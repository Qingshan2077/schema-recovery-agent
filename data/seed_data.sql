USE schema_recovery_demo;

INSERT INTO users (id, username, email, phone, status) VALUES
(1,'alice','alice@example.com','18800000001',1),
(2,'bob','bob@example.com','18800000002',1),
(3,'carol','carol@example.com','18800000003',1),
(4,'dave','dave@example.com','18800000004',0),
(5,'erin','erin@example.com','18800000005',1);

INSERT INTO user_profiles (id, user_id, avatar_url, bio, birthday, gender) VALUES
(1,1,'/a.png','VIP buyer','1990-01-01','F'),(2,2,'/b.png','New user','1991-02-02','M'),
(3,3,'/c.png','Reviewer','1992-03-03','F'),(4,4,'/d.png','Inactive','1993-04-04','M'),
(5,5,'/e.png','Collector','1994-05-05','F');

INSERT INTO user_addresses (id, user_id, province, city, detail_address, is_default) VALUES
(1,1,'Zhejiang','Hangzhou','Road 1',1),(2,1,'Shanghai','Shanghai','Road 2',0),
(3,2,'Jiangsu','Nanjing','Road 3',1),(4,3,'Guangdong','Shenzhen','Road 4',1),
(5,5,'Beijing','Beijing','Road 5',1);

INSERT INTO roles (id, role_name, role_code) VALUES
(1,'Admin','ADMIN'),(2,'Buyer','BUYER'),(3,'Seller','SELLER'),(4,'Ops','OPS'),(5,'Guest','GUEST');

INSERT INTO user_roles (user_id, role_id) VALUES (1,1),(1,2),(2,2),(3,2),(4,5);

INSERT INTO categories (id, parent_id, name, sort_order) VALUES
(1,NULL,'Electronics',1),(2,1,'Phones',1),(3,1,'Computers',2),(4,NULL,'Home',2),(5,4,'Kitchen',1);

INSERT INTO suppliers (id, supplier_code, name, contact_phone) VALUES
(1,'SUP-A','Alpha Supply','400-001'),(2,'SUP-B','Beta Supply','400-002'),
(3,'SUP-C','Gamma Supply','400-003'),(4,'SUP-D','Delta Supply','400-004'),(5,'SUP-E','Epsilon Supply','400-005');

INSERT INTO products (id, name, category_id, supplier_code, price, status) VALUES
(1,'Phone Mini',2,'SUP-A',1999.00,'active'),(2,'Phone Pro',2,'SUP-A',4999.00,'active'),
(3,'Laptop Air',3,'SUP-B',6999.00,'active'),(4,'Blender',5,'SUP-C',299.00,'active'),
(5,'Desk Lamp',4,'SUP-D',99.00,'inactive');

INSERT INTO product_sku (id, product_id, sku_code, spec_json, price) VALUES
(1,1,'SKU-PM-64','{"color":"black","storage":"64G"}',1999.00),
(2,1,'SKU-PM-128','{"color":"white","storage":"128G"}',2299.00),
(3,2,'SKU-PP-256','{"color":"blue","storage":"256G"}',4999.00),
(4,3,'SKU-LA-16','{"memory":"16G"}',6999.00),
(5,4,'SKU-BL-1','{"size":"standard"}',299.00);

INSERT INTO product_images (id, product_id, image_url, sort_order) VALUES
(1,1,'/p1-1.png',1),(2,1,'/p1-2.png',2),(3,2,'/p2.png',1),(4,3,'/p3.png',1),(5,4,'/p4.png',1);

INSERT INTO warehouses (id, warehouse_code, name, city) VALUES
(1,'WH-HZ','Hangzhou Main','Hangzhou'),(2,'WH-SH','Shanghai East','Shanghai'),
(3,'WH-BJ','Beijing North','Beijing'),(4,'WH-SZ','Shenzhen South','Shenzhen'),(5,'WH-CD','Chengdu West','Chengdu');

INSERT INTO inventory (id, product_id, sku_id, warehouse_id, quantity) VALUES
(1,1,1,1,100),(2,1,2,1,80),(3,2,3,2,60),(4,3,4,3,40),(5,4,5,4,200);

INSERT INTO supplier_products (supplier_id, product_id, supplier_sku) VALUES
(1,1,'A-P1'),(1,2,'A-P2'),(2,3,'B-P3'),(3,4,'C-P4'),(4,5,'D-P5');

INSERT INTO warehouse_stock (id, warehouse_id, product_id, sku_id, available_qty, locked_qty) VALUES
(1,1,1,1,80,20),(2,1,1,2,70,10),(3,2,2,3,50,10),(4,3,3,4,35,5),(5,4,4,5,180,20);

INSERT INTO coupons (id, coupon_code, title, discount_amount, valid_from, valid_to) VALUES
(1,'C10','Ten off',10,'2026-01-01','2026-12-31'),(2,'C20','Twenty off',20,'2026-01-01','2026-12-31'),
(3,'C50','Fifty off',50,'2026-01-01','2026-12-31'),(4,'NEW','New user',30,'2026-01-01','2026-12-31'),
(5,'VIP','VIP coupon',100,'2026-01-01','2026-12-31');

INSERT INTO orders (id, user_id, order_no, status, total_amount, coupon_id, created_at) VALUES
(1,1,'O2026001','paid',1999.00,1,'2026-07-01 10:00:00'),(2,1,'O2026002','paid',4999.00,2,'2026-07-01 11:00:00'),
(3,2,'O2026003','shipped',6999.00,NULL,'2026-07-02 12:00:00'),(4,3,'O2026004','pending',299.00,4,'2026-07-03 13:00:00'),
(5,5,'O2026005','paid',99.00,NULL,'2026-07-04 14:00:00');

INSERT INTO order_items (id, order_id, product_id, sku_id, quantity, price) VALUES
(1,1,1,1,1,1999.00),(2,2,2,3,1,4999.00),(3,3,3,4,1,6999.00),(4,4,4,5,1,299.00),(5,5,5,NULL,1,99.00);

INSERT INTO order_payments (id, order_id, payment_no, payment_method, amount, paid_at) VALUES
(1,1,'P001','wechat',1999,'2026-07-01 10:05:00'),(2,2,'P002','alipay',4999,'2026-07-01 11:05:00'),
(3,3,'P003','card',6999,'2026-07-02 12:05:00'),(4,4,'P004','wechat',299,NULL),(5,5,'P005','alipay',99,'2026-07-04 14:05:00');

INSERT INTO shipping_companies (id, company_code, name, hotline) VALUES
(1,'SF','SF Express','95338'),(2,'YTO','YTO','95554'),(3,'ZTO','ZTO','95311'),(4,'JD','JD Logistics','950616'),(5,'EMS','EMS','11183');

INSERT INTO order_shipments (id, order_id, shipping_company_id, tracking_no, shipped_at) VALUES
(1,1,1,'SF001','2026-07-01 18:00:00'),(2,2,2,'YTO002','2026-07-01 19:00:00'),
(3,3,3,'ZTO003','2026-07-02 20:00:00'),(4,4,4,'JD004',NULL),(5,5,5,'EMS005','2026-07-04 21:00:00');

INSERT INTO user_coupons (id, user_id, coupon_id, status) VALUES
(1,1,1,'used'),(2,1,2,'used'),(3,2,3,'unused'),(4,3,4,'used'),(5,5,5,'unused');

INSERT INTO coupon_usage (id, user_coupon_id, order_id, used_at) VALUES
(1,1,1,'2026-07-01 10:00:00'),(2,2,2,'2026-07-01 11:00:00'),(3,4,4,'2026-07-03 13:00:00'),
(4,3,3,'2026-07-02 12:00:00'),(5,5,5,'2026-07-04 14:00:00');

INSERT INTO reviews (id, user_id, product_id, order_item_id, rating, content) VALUES
(1,1,1,1,5,'Great'),(2,1,2,2,4,'Good'),(3,2,3,3,5,'Excellent'),(4,3,4,4,3,'OK'),(5,5,5,5,2,'Average');

INSERT INTO review_images (id, review_id, image_url, sort_order) VALUES
(1,1,'/r1.png',1),(2,2,'/r2.png',1),(3,3,'/r3.png',1),(4,4,'/r4.png',1),(5,5,'/r5.png',1);

INSERT INTO cart_items (id, user_id, product_id, sku_id, quantity) VALUES
(1,1,3,4,1),(2,2,1,1,2),(3,3,2,3,1),(4,4,4,5,1),(5,5,1,2,1);

INSERT INTO wishlist (id, user_id, product_id) VALUES (1,1,2),(2,2,3),(3,3,1),(4,4,4),(5,5,5);

INSERT INTO operations_log (id, operator_id, operation_type, target_table, target_id, content) VALUES
(1,1,'CREATE','orders',1,'create order'),(2,2,'UPDATE','products',1,'update product'),(3,1,'DELETE','cart_items',1,'delete cart'),
(4,3,'LOGIN','users',3,'login'),(5,4,'EXPORT','orders',2,'export');

INSERT INTO notifications (id, user_id, title, content, read_flag) VALUES
(1,1,'Paid','Order paid',1),(2,2,'Shipped','Order shipped',0),(3,3,'Coupon','New coupon',0),(4,4,'Welcome','Welcome',1),(5,5,'Review','Please review',0);

INSERT INTO sys_config (id, config_key, config_value, description) VALUES
(1,'site_name','Demo Mall','site'),(2,'currency','CNY','currency'),(3,'shipping_free_threshold','99','shipping'),(4,'review_enabled','true','review'),(5,'coupon_enabled','true','coupon');

INSERT INTO data_dictionary (id, dict_type, dict_key, dict_value, sort_order) VALUES
(1,'order_status','pending','Pending',1),(2,'order_status','paid','Paid',2),(3,'order_status','shipped','Shipped',3),(4,'user_status','1','Active',1),(5,'user_status','0','Inactive',2);
