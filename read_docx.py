from docx import Document
import sys

def read_docx(file_path):
    print(f"Reading {file_path}")
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            if para.text.strip():
                print(para.text)
    except Exception as e:
        print(f"Error reading: {e}")

if __name__ == "__main__":
    read_docx(r'C:\Users\newsh\OneDrive\Documents\Jobs\PLYGROUND\models\Sample Financial Modelling Software.docx')
