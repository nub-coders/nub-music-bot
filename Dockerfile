FROM python:3.13

# Install ffmpeg, git, and curl
RUN apt-get update && \
    apt-get install -y ffmpeg git curl unzip && \
    rm -rf /var/lib/apt/lists/*

# Install Deno runtime
RUN curl -fsSL https://deno.land/install.sh | sh && \
    mv /root/.deno/bin/deno /usr/local/bin/deno

# Configure git with rebase true
RUN git config --global pull.rebase true

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create startup script that pulls latest changes and runs the app
RUN echo '#!/bin/bash\nif [ -d ".git" ]; then\n  echo "Pulling latest changes..."\n  git pull\nfi\necho "Starting application..."\npython3 main.py' > start.sh && \
    chmod +x start.sh

# Default command
CMD ["./start.sh"]
