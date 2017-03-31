import sandman2
app = sandman2.get_app('sqlite+pysqlite:///scanner.db')
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
app.run(host='0.0.0.0', port=5000)
