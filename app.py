import os
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return 'Welcome to WordGuess!'

@app.route('/play')
def play_game():
    # Logic for playing the game
    return 'This is the WordGuess game!'

@app.route('/submit')
def submit_guess():
    # Logic for submitting a guess
    guess = request.args.get('guess')
    # Check if guess is correct and return appropriate response
    return jsonify({'result': 'correct'}) if guess == 'apple' else jsonify({'result': 'incorrect'})

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', False)
    app.run(host='0.0.0.0', port=5000, debug=debug)
