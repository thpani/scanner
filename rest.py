#!/usr/bin/env python3

from flask import request, g, Flask, Response
from flask_restful import Resource, Api, reqparse
import sqlite3

DATABASE = 'scanner.db'

app = Flask(__name__)
api = Api(app)

# DB helpers
# http://flask.pocoo.org/docs/0.12/patterns/sqlite3/

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

def make_dicts(cursor, row):
    return dict((cursor.description[idx][0], value)
                for idx, value in enumerate(row))

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    db.row_factory = make_dicts
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

# add CORS header
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


class List(Resource):
    def get(self, id):
        return query_db('SELECT id, name FROM lists WHERE id = ?', (id,), True)

    def delete(self, id):
        db = get_db()
        db.execute('DELETE FROM lists WHERE id=?', (id,))
        db.commit()
        return '', 204

    def put(self, id):
        parser = reqparse.RequestParser()
        parser.add_argument('name')
        args = parser.parse_args()
        db = get_db()
        db.execute('UPDATE lists SET name=? WHERE id=?', (args.name, id))
        db.commit()
        return '', 201

    def options(self, id):
        resp = Response()
        resp.headers["Access-Control-Allow-Methods"] = "PUT,DELETE"
        return resp

class ListList(Resource):
    def get(self):
        return query_db('SELECT id, name FROM lists')

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('id', type=int)
        parser.add_argument('name')
        args = parser.parse_args()
        db = get_db()
        db.execute('INSERT INTO lists (id, name) VALUES (?, ?)', (args.id, args.name))
        db.commit()
        return '', 201

class Product(Resource):
    def get(self, ean):
        return query_db('SELECT ean, name, list FROM products WHERE ean = ?', (ean,), True)

    def delete(self, ean):
        db = get_db()
        db.execute('DELETE FROM products WHERE ean=?', (ean,))
        db.commit()
        return '', 204

    def put(self, ean):
        parser = reqparse.RequestParser()
        parser.add_argument('name')
        parser.add_argument('list', type=int)
        args = parser.parse_args()
        db = get_db()
        # TODO
        db.execute('UPDATE products SET name=?, list=? WHERE ean=?', (args.name, args.list, ean))
        db.commit()
        return '', 201

    def options(self, ean):
        resp = Response()
        resp.headers["Access-Control-Allow-Methods"] = "PUT,DELETE"
        return resp

class ProductList(Resource):
    def get(self):
        return query_db('SELECT ean, name, list FROM products')

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('ean', type=int)
        parser.add_argument('name')
        args = parser.parse_args()
        db = get_db()
        # TODO
        db.execute('INSERT INTO products (ean, name) VALUES (?, ?)', (args.ean, args.name))
        db.commit()
        return '', 201

api.add_resource(ListList, '/lists')
api.add_resource(List, '/lists/<id>')
api.add_resource(ProductList, '/products')
api.add_resource(Product, '/products/<ean>')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
