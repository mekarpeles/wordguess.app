# Use an official Python runtime as a parent image
FROM python:3.9.7-slim

# Set the working directory to /app
WORKDIR /app

# Install necessary system packages
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libbsd0 libmd0 mg \

# Install Node.js and Vue CLI
RUN curl -sL https://deb.nodesource.com/setup_14.x | bash -
RUN apt-get install -y nodejs
#RUN npm install -g @vue/cli

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_DEBUG=1

# Expose port 5000 for Flask
EXPOSE 5000

# Start the Flask app
CMD ["python", "app.py"]
