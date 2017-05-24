#!/usr/bin/env python3

import errno
import os
import sqlite3
import sys

from flask import request, g, Flask, Response
from flask_restful import Resource, Api, reqparse

DATABASE = '/var/db/scanner/scanner.db'

app = Flask(__name__, static_folder='client', static_url_path='')
api = Api(app)

# DB helpers
# http://flask.pocoo.org/docs/0.12/patterns/sqlite3/

def init_db():
    mkdir_p(os.path.dirname(DATABASE))
    with app.app_context():
        db = get_db()
        spath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schema.sql')
        with app.open_resource(spath, mode='r') as f:
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

# serve index.html as /
@app.route('/')
def root():
    return app.send_static_file('index.html')

# http://stackoverflow.com/a/600612/1161037
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

##
## REST resources
##

class Tag(Resource):
    def get(self, id):
        return query_db('SELECT id, name, ord FROM tags WHERE id = ?', (id,), True)

    def delete(self, id):
        db = get_db()
        db.execute('DELETE FROM tags WHERE id=?', (id,))
        db.commit()
        return '', 204

    def put(self, id):
        parser = reqparse.RequestParser()
        parser.add_argument('name')
        parser.add_argument('ord')
        args = parser.parse_args()
        db = get_db()
        db.execute('UPDATE tags SET name=?, ord=? WHERE id=?', (args.name, args.ord, id))
        db.commit()
        return '', 201

    def options(self, id):
        resp = Response()
        resp.headers["Access-Control-Allow-Methods"] = "PUT,DELETE"
        return resp

class TagProductList(Resource):
    def get(self):
        tags = query_db('SELECT id, name, ord FROM tags ORDER BY ord')
        for tag in tags:
            tag['products'] = query_db('SELECT ean, name FROM products WHERE tag = ?', (tag['id'],))
        return tags

class TagList(Resource):
    def get(self):
        return query_db('SELECT id, name, ord FROM tags ORDER BY ord')

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('id', type=int)
        parser.add_argument('name')
        parser.add_argument('ord')
        args = parser.parse_args()
        db = get_db()
        db.execute('INSERT INTO tags (id, name, ord) VALUES (?, ?, ?)', (args.id, args.name, args.ord))
        db.commit()
        return '', 201

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
        return query_db('SELECT ean, name, list, tag, shelf FROM products WHERE ean = ?', (ean,), True)

    def delete(self, ean):
        db = get_db()
        db.execute('DELETE FROM products WHERE ean=?', (ean,))
        db.commit()
        return '', 204

    def put(self, ean):
        parser = reqparse.RequestParser()
        parser.add_argument('name')
        parser.add_argument('list', type=int)
        parser.add_argument('tag', type=int)
        parser.add_argument('shelf')
        args = parser.parse_args()
        db = get_db()
        db.execute('UPDATE products SET name=?, list=?, tag=?, shelf=? WHERE ean=?', (args.name, args.list, args.tag, args.shelf, ean))
        db.commit()
        return '', 201

    def options(self, ean):
        resp = Response()
        resp.headers["Access-Control-Allow-Methods"] = "PUT,DELETE"
        return resp

class ProductList(Resource):
    def get(self):
        return query_db('SELECT ean, name, list, tag, shelf FROM products ORDER BY list, shelf')

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('ean', type=int)
        parser.add_argument('name')
        parser.add_argument('list', type=int)
        parser.add_argument('tag', type=int)
        parser.add_argument('shelf')
        args = parser.parse_args()
        db = get_db()
        db.execute('INSERT INTO products (ean, name, list, tag, shelf) VALUES (?, ?, ?, ?, ?)', (args.ean, args.name, args.list, args.tag, args.shelf))
        db.commit()
        return '', 201

api.add_resource(TagProductList, '/tags/products')
api.add_resource(TagList, '/tags')
api.add_resource(Tag, '/tags/<int:id>')
api.add_resource(ListList, '/lists')
api.add_resource(List, '/lists/<int:id>')
api.add_resource(ProductList, '/products')
api.add_resource(Product, '/products/<int:ean>')

if __name__ == '__main__':
    init_db()
    debug = len(sys.argv) > 1 and sys.argv[1] == '--debug'
    app.run(host='0.0.0.0', debug=debug)
