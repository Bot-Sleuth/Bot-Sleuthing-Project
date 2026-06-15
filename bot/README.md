# Test Bot
This bot is for [this test survey](https://uwmadison.co1.qualtrics.com/jfe/form/SV_4G6ZhkhvlltLjQW).

## Requirements
* Python3
* Pip

## Setup
These instructions are only tested on Mac/Linux (Ubuntu):
1. Create and source virtual environment:
    ```bash
    python3 -m venv venv-bot
    source venv-bot/bin/activate
    ```
2. Install Dependencies:
    ```bash
    pip install -r bot/requirements.txt
    ```
3. Create a `.env` file in the `/bot` folder ith your [OpenAI API key](https://platform.openai.com/api-keys). The format of the .env file needs to be:
    ```bash
    OPENAI_API_KEY=your_api_key_here
    ```

## Running
This will fill in the survey. You will see a window pop up with the survey that gets gradually filled-in.
```bash
python3 bot/bot.py --visible
```


## Optional: Docker
If you would like to use Docker instead (if you have it installed), you can run:
```bash
cd bot
docker build -t sleuth-bot-image .
docker run --rm --name sleuth-bot-container --env-file .env sleuth-bot-image
```

