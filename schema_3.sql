BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY, name TEXT, ord INTEGER);
CREATE TEMPORARY TABLE products_backup(ean, name, shelf, list);
INSERT INTO products_backup SELECT ean, name, shelf, list FROM products;
DROP TABLE products;
CREATE TABLE products (ean TEXT PRIMARY KEY, name TEXT, shelf TEXT, list INTEGER, tag INTEGER, FOREIGN KEY (list) REFERENCES lists (id), FOREIGN KEY (tag) REFERENCES tags (id));
INSERT INTO products (ean, name, shelf, list) SELECT ean, name, shelf, list FROM products_backup;
DROP TABLE products_backup;
UPDATE version SET major=3;
COMMIT;
