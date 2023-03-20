import os
import openai
openai.api_key = os.environ.get('OPENAI_API_KEY', '')


def query_gpt(prompt):
    response = openai.Completion.create(
        engine="text-davinci-002",
        prompt=prompt,
        temperature=0.7,
        max_tokens=1024,
        n=1,
        stop=None,
        timeout=30,
    ).choices[0].text
    print(response)
    return response


def continue_game(history):
    response = query_gpt(history)
    history += f"{response}\n"
    return history, response


def create_game(language="Chinese"):
    prompt = (
        "Welcome to WordGuess! You are playing a language learning game based "
        "on Taboo and you are the AI game master called TabooGPT. Each round "
        "you will choose a secret 'taboo' word or phrase you're not allowed "
        "to use in the target language of {language}. Your teammate is trying "
        "to guess the 'taboo' word. You'll provide hints and clues in the "
        "target language one message at a time without using the taboo word. "
        "If your teammate needs to ask clarifying questions or guesses in "
        "their native language, that's okay. Here's an example of what a "
        "completed game may look like. It will actually happen on message "
        "at a time, in turns:\n"
	"```\n\n"
        "TabooGPT: 🔴它是紅色的 (Tā shì hóngsè de)\n"
        "Player: 一個fire truck?\n"
        "TabooGPT: 這不是救火車. 🚒 可以吃 🍔 (Zhè jiùhuǒ chē. Kěyǐ chī)\n"
        "Player: 是西紅柿嗎?\n"
        "TabooGPT: 不是。味道很甜 Bù shì. Wèidào hěn tián.\n"
        "Player: What does weidao mean?"
        "TabooGPT: It refers to the taste 👅\n"
        "Player: 一個貧國!\n"
        "TabooGPT: 沒錯讓我們再玩一次 Méicuò ràng wǒmen zài wán yīcì 🎉  它非常鋒利 Tā fēicháng fēnglì\n"
        "```\n\n"
        "You will now start the game by choosing a secret taboo word and providing the first hint.\n"
    )
    return continue_game(prompt)
