FROM python:3.11
RUN apt update && apt install -y chromium-driver
ADD . /bot
WORKDIR /bot
RUN pip install -r requirements.txt
CMD ["python3", "-u", "bot.py"]