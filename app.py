from flask import Flask, render_template, jsonify
import random
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/status')
def status():
    connected = True # TODO : if raspberryPi can enable, edit this code
    if connected:
        return jsonify({
            "connected": connected,
            "x": 0,
            "y": 0,
            "state" : "waiting"
        })
    else:
        return jsonify({
            "connected": False
        })

if __name__ == '__main__':
    app.run(debug=True)
