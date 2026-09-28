from flask import Flask, jsonify, request

app = Flask(__name__)

@app.post('/cloud/ingest')
def ingest():
    payload = request.get_json(force=True)
    print('CLOUD RECEIVED:', payload)
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001)
