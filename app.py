import os
import openai
import apis.gpt
from flask import Flask, request, jsonify, render_template, session

app = Flask(__name__)

history = ""

@app.route('/')
def index():
    return 'Welcome to WordGuess!'


@app.route('/play')
def play_game():
    # Logic for playing the game
    global history
    guess = request.args.get('guess')
    if guess:
        history += f"{history}\nPlayer: {guess}\n"
        history, response = apis.gpt.continue_game(history)
        return jsonify({'result': response, 'history': history})
    history, response = apis.gpt.create_game()
    return render_template('play.html', msg=response)


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', False)
    app.secret_key = os.environ.get('FLASK_SECRET', "default-app-secret")
    app.run(host='0.0.0.0', port=5000, debug=debug)
