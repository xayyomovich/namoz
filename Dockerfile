# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements file first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your bot's code
COPY . .

# Set environment variables
ENV PORT=8080

# Command to run your bot
CMD ["python", "-m", "src.bot.bot"]










