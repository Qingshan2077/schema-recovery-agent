USE schema_recovery_demo;

DROP VIEW IF EXISTS vw_order_summary;
DROP VIEW IF EXISTS vw_product_ranking;
DROP VIEW IF EXISTS vw_user_coupon_summary;
DROP PROCEDURE IF EXISTS sp_get_user_orders;
DROP PROCEDURE IF EXISTS sp_get_order_detail;
DROP PROCEDURE IF EXISTS sp_get_user_profile;
DROP PROCEDURE IF EXISTS sp_get_top_products;
DROP PROCEDURE IF EXISTS sp_get_product_reviews;
DROP PROCEDURE IF EXISTS sp_get_inventory_summary;
DROP PROCEDURE IF EXISTS sp_get_user_coupons;
DROP PROCEDURE IF EXISTS sp_get_daily_sales_report;

DELIMITER //

CREATE PROCEDURE sp_get_user_orders(IN p_user_id BIGINT)
BEGIN
    SELECT o.*, u.username
    FROM orders o
    JOIN users u ON o.user_id = u.id
    WHERE o.user_id = p_user_id;
END//

CREATE PROCEDURE sp_get_order_detail(IN p_order_id BIGINT)
BEGIN
    SELECT o.order_no, o.total_amount, o.status,
           oi.product_id, oi.quantity, oi.price,
           p.name AS product_name, u.username
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN products p ON oi.product_id = p.id
    JOIN users u ON o.user_id = u.id
    WHERE o.id = p_order_id;
END//

CREATE PROCEDURE sp_get_user_profile(IN p_user_id BIGINT)
BEGIN
    SELECT u.username, u.email, up.avatar_url, up.bio, ua.province, ua.city
    FROM users u
    LEFT JOIN user_profiles up ON u.id = up.user_id
    LEFT JOIN user_addresses ua ON u.id = ua.user_id
    WHERE u.id = p_user_id;
END//

CREATE PROCEDURE sp_get_top_products(IN p_limit INT)
BEGIN
    SELECT p.id, p.name, p.price,
           (SELECT COALESCE(AVG(r.rating), 0) FROM reviews r WHERE r.product_id = p.id) AS avg_rating,
           (SELECT COUNT(*) FROM order_items oi WHERE oi.product_id = p.id) AS total_sold
    FROM products p
    ORDER BY total_sold DESC
    LIMIT p_limit;
END//

CREATE PROCEDURE sp_get_product_reviews(IN p_product_id BIGINT)
BEGIN
    SELECT r.id, r.rating, r.content, u.username, ri.image_url
    FROM reviews r
    JOIN users u ON r.user_id = u.id
    LEFT JOIN review_images ri ON r.id = ri.review_id
    WHERE r.product_id = p_product_id;
END//

CREATE PROCEDURE sp_get_inventory_summary(IN p_product_id BIGINT)
BEGIN
    SELECT p.name, w.name AS warehouse_name, ws.available_qty, ws.locked_qty
    FROM warehouse_stock ws
    JOIN products p ON ws.product_id = p.id
    JOIN warehouses w ON ws.warehouse_id = w.id
    WHERE ws.product_id = p_product_id;
END//

CREATE PROCEDURE sp_get_user_coupons(IN p_user_id BIGINT)
BEGIN
    SELECT uc.id, uc.status, c.coupon_code, c.title, c.discount_amount
    FROM user_coupons uc
    JOIN coupons c ON uc.coupon_id = c.id
    JOIN users u ON uc.user_id = u.id
    WHERE u.id = p_user_id;
END//

CREATE PROCEDURE sp_get_daily_sales_report(IN p_day DATE)
BEGIN
    SELECT DATE(o.created_at) AS order_day, p.category_id, c.name AS category_name,
           SUM(oi.quantity) AS quantity, SUM(oi.quantity * oi.price) AS amount
    FROM orders o
    JOIN order_items oi ON o.id = oi.order_id
    JOIN products p ON oi.product_id = p.id
    JOIN categories c ON p.category_id = c.id
    WHERE DATE(o.created_at) = p_day
    GROUP BY DATE(o.created_at), p.category_id, c.name;
END//

DELIMITER ;

CREATE VIEW vw_order_summary AS
SELECT o.id, o.order_no, u.username, o.total_amount, o.status, o.created_at
FROM orders o
JOIN users u ON o.user_id = u.id;

CREATE VIEW vw_product_ranking AS
SELECT p.id, p.name, c.name AS category_name, COUNT(oi.id) AS total_orders
FROM products p
JOIN categories c ON p.category_id = c.id
LEFT JOIN order_items oi ON p.id = oi.product_id
GROUP BY p.id, p.name, c.name;

CREATE VIEW vw_user_coupon_summary AS
SELECT u.id, u.username, COUNT(uc.id) AS coupon_count
FROM users u
LEFT JOIN user_coupons uc ON u.id = uc.user_id
GROUP BY u.id, u.username;
