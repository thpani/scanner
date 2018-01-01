BEGIN TRANSACTION;
CREATE TEMPORARY TABLE products_backup(ean, name, list);
INSERT INTO products_backup SELECT ean, name, list FROM products;
DROP TABLE products;
CREATE TABLE products (ean TEXT PRIMARY KEY, name TEXT, shelf TEXT, list INTEGER, FOREIGN KEY (list) REFERENCES lists (id));
INSERT INTO products (ean, name, list) SELECT ean, name, list FROM products_backup;
DROP TABLE products_backup;
UPDATE version SET major=2;
COMMIT;
