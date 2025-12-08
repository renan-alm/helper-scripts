.PHONY: bootstrap server clean

bootstrap: clean
	@echo "Starting callback server on port 3000..."
	python3 callback-server.py --port 3000 &
	@sleep 1
	@echo "Starting ngrok tunnel..."
	@ngrok http 3000

prep-server:
	export GITHUB_TOKEN=$$(cat ~/.renan/github_token) && \
	python3 -m venv venv && \
	. venv/bin/activate && \
	python -m pip install --upgrade pip && \
	pip install -r requirements.txt;

server:
	python callback-server.py

clean:
	pkill -f callback-server.py || true
	pkill -f ngrok || true

debug:
	ps -ef | grep -i ngrok
