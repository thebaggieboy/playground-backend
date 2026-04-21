"""
PDF Export Module
Exports financial models to professional PDF format
Uses reportlab for PDF generation
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from decimal import Decimal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Color palette
# ────────────────────────────────────────────────────────────────────────────
PRIMARY  = colors.HexColor('#1a1a2e')
ACCENT   = colors.HexColor('#0066ff')
HEADER   = colors.HexColor('#f0f4f8')
ROW_ALT  = colors.HexColor('#f8fafc')
TEXT     = colors.HexColor('#1e293b')
MUTED    = colors.HexColor('#64748b')
SUCCESS  = colors.HexColor('#059669')
DANGER   = colors.HexColor('#dc2626')


class PDFExporter:
    """
    Exports financial scenarios to professional PDF reports.
    """

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._add_custom_styles()

    def _add_custom_styles(self):
        self.styles.add(ParagraphStyle(
            'CoverTitle', parent=self.styles['Title'],
            fontSize=28, textColor=PRIMARY, spaceAfter=12,
        ))
        self.styles.add(ParagraphStyle(
            'CoverSubtitle', parent=self.styles['Normal'],
            fontSize=14, textColor=MUTED, spaceAfter=30,
        ))
        self.styles.add(ParagraphStyle(
            'SectionHeader', parent=self.styles['Heading2'],
            fontSize=16, textColor=PRIMARY, spaceBefore=20, spaceAfter=10,
        ))
        self.styles.add(ParagraphStyle(
            'MetaLabel', parent=self.styles['Normal'],
            fontSize=9, textColor=MUTED,
        ))
        self.styles.add(ParagraphStyle(
            'MetaValue', parent=self.styles['Normal'],
            fontSize=11, textColor=TEXT, fontName='Helvetica-Bold',
        ))

    # ────────────────────────────────────────────────────────────────────────
    # Public API
    # ────────────────────────────────────────────────────────────────────────

    def export_scenario(self, scenario):
        """
        Export single scenario to PDF.
        Returns: BytesIO buffer with PDF content
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            rightMargin=1.5 * cm,
            leftMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=1.5 * cm,
        )

        elements = []

        # Cover page
        elements += self._build_cover(scenario)
        elements.append(PageBreak())

        # Build statement pages from calculated data
        from .models import CalculatedStatement

        statement_configs = [
            ('is', 'Income Statement'),
            ('bs', 'Balance Sheet'),
            ('cfs', 'Cash Flow Statement'),
            ('ratio', 'Financial Ratios'),
            ('debt', 'Debt Schedule'),
            ('valuation', 'Valuation Metrics'),
        ]

        for stmt_type, title in statement_configs:
            stmts = CalculatedStatement.objects.filter(
                scenario=scenario,
                statement_type=stmt_type
            )
            if stmts.exists():
                elements += self._build_statement_page(title, stmts, stmt_type)
                elements.append(PageBreak())

        # Build the PDF
        doc.build(elements, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        buffer.seek(0)
        return buffer

    # ────────────────────────────────────────────────────────────────────────
    # Cover page
    # ────────────────────────────────────────────────────────────────────────

    def _build_cover(self, scenario):
        elements = []

        elements.append(Spacer(1, 3 * cm))

        # Title
        model_name = scenario.model.name if scenario.model else 'Financial Model'
        elements.append(Paragraph(model_name, self.styles['CoverTitle']))

        # Subtitle
        elements.append(Paragraph(
            f'{scenario.name} — {scenario.get_scenario_type_display()} Case',
            self.styles['CoverSubtitle']
        ))

        elements.append(HRFlowable(
            width='60%', thickness=2, color=ACCENT,
            spaceAfter=20, spaceBefore=10
        ))

        # Metadata table
        meta_data = [
            ['Generated', datetime.now().strftime('%B %d, %Y at %H:%M')],
            ['Model Owner', scenario.model.owner.email if scenario.model else 'N/A'],
            ['Scenario Type', scenario.get_scenario_type_display()],
        ]

        # Add project info if available
        try:
            pi = scenario.project_info
            meta_data += [
                ['Project Type', pi.project_type],
                ['Location', pi.project_location],
                ['Capacity', f'{pi.total_capacity:,.0f} {pi.capacity_unit}'],
            ]
        except Exception:
            pass

        # Add macro info
        try:
            macro = scenario.macro_assumptions
            meta_data += [
                ['Base Year', str(macro.base_year)],
                ['Forecast Periods', f'{macro.number_of_years} years'],
                ['Discount Rate (WACC)', f'{macro.discount_rate_wacc}%'],
                ['Currency', macro.reporting_currency],
            ]
        except Exception:
            pass

        meta_table = Table(meta_data, colWidths=[3 * inch, 5 * inch])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
            ('TEXTCOLOR', (1, 0), (1, -1), TEXT),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(meta_table)

        return elements

    # ────────────────────────────────────────────────────────────────────────
    # Financial statement pages
    # ────────────────────────────────────────────────────────────────────────

    def _build_statement_page(self, title, statements, stmt_type):
        elements = []

        elements.append(Paragraph(title, self.styles['SectionHeader']))

        if stmt_type == 'valuation':
            # Valuation is a single row of key-value metrics
            return elements + self._build_valuation_section(statements)

        # Get periods from first statement
        first = statements.first()
        if not first or not first.values_by_period:
            elements.append(Paragraph('No data available.', self.styles['Normal']))
            return elements

        periods = sorted(first.values_by_period.keys())

        # Limit to 15 periods max for readability
        display_periods = periods[:15]

        # Build header row
        header = ['Line Item'] + display_periods

        # Build data rows
        data = [header]
        highlight_items = {
            'Total Revenue', 'EBITDA', 'EBIT', 'Net Income',
            'Total Assets', 'Total Liabilities', 'Total Equity',
            'Cash Flow from Operations', 'Net Cash Flow', 'Cash Balance (End)',
            'Closing Balance', 'DSCR',
        }

        for stmt in statements:
            row = [stmt.line_item]
            for p in display_periods:
                val = stmt.values_by_period.get(p, 0)
                if isinstance(val, (int, float, Decimal)):
                    val = float(val)
                    if stmt_type == 'ratio':
                        if '%' in stmt.line_item:
                            row.append(f'{val:.1f}%')
                        else:
                            row.append(f'{val:.2f}')
                    else:
                        if abs(val) >= 1e6:
                            row.append(f'{val / 1e6:,.2f}M')
                        else:
                            row.append(f'{val:,.0f}')
                else:
                    row.append(str(val))
            data.append(row)

        # Calculate column widths
        label_width = 3.5 * inch
        num_cols = len(display_periods)
        available_width = landscape(A4)[0] - 3 * cm - label_width
        col_width = min(available_width / max(num_cols, 1), 1.8 * cm)
        col_widths = [label_width] + [col_width] * num_cols

        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Style the table
        style_cmds = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),

            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('TEXTCOLOR', (0, 1), (-1, -1), TEXT),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),

            # Grid
            ('LINEBELOW', (0, 0), (-1, 0), 1, PRIMARY),
            ('LINEBELOW', (0, -1), (-1, -1), 0.5, MUTED),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ]

        # Highlight key rows
        for i, row_data in enumerate(data[1:], start=1):
            if row_data[0] in highlight_items:
                style_cmds.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), HEADER))

            # Color negative values red
            for j, cell in enumerate(row_data[1:], start=1):
                if isinstance(cell, str) and cell.startswith('-'):
                    style_cmds.append(('TEXTCOLOR', (j, i), (j, i), DANGER))

        table.setStyle(TableStyle(style_cmds))
        elements.append(table)

        return elements

    def _build_valuation_section(self, statements):
        elements = []
        for stmt in statements:
            if stmt.values_by_period:
                data = []
                for key, val in stmt.values_by_period.items():
                    if isinstance(val, (int, float, Decimal)):
                        val = float(val)
                        if '%' in key:
                            formatted = f'{val:.2f}%'
                        elif abs(val) >= 1e6:
                            formatted = f'${val / 1e6:,.2f}M'
                        else:
                            formatted = f'${val:,.2f}'
                    else:
                        formatted = str(val)
                    data.append([key, formatted])

                if data:
                    table = Table(data, colWidths=[4 * inch, 4 * inch])
                    table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
                        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 11),
                        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
                        ('TEXTCOLOR', (1, 0), (1, -1), TEXT),
                        ('TOPPADDING', (0, 0), (-1, -1), 8),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#e2e8f0')),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                    ]))
                    elements.append(table)

        return elements

    # ────────────────────────────────────────────────────────────────────────
    # Page footer
    # ────────────────────────────────────────────────────────────────────────

    def _page_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MUTED)

        page_width = landscape(A4)[0]

        # Left: branding
        canvas.drawString(
            1.5 * cm, 0.75 * cm,
            'Generated by Playground Financial Modeling Platform'
        )

        # Right: page number
        canvas.drawRightString(
            page_width - 1.5 * cm, 0.75 * cm,
            f'Page {doc.page}'
        )

        # Top rule
        canvas.setStrokeColor(colors.HexColor('#e2e8f0'))
        canvas.line(1.5 * cm, landscape(A4)[1] - 1.5 * cm, page_width - 1.5 * cm, landscape(A4)[1] - 1.5 * cm)

        canvas.restoreState()
