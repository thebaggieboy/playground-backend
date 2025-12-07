FROM python:3.9

ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port (Render will set the PORT environment variable)
EXPOSE $PORT

# Use a shell script to handle environment variable substitution
CMD ["sh", "-c", "daphne --bind 0.0.0.0 --port $PORT playground.asgi:application"]