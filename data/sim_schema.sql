CREATE DATABASE IF NOT EXISTS schema_recovery_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE schema_recovery_demo;

DROP TABLE IF EXISTS data_dictionary, sys_config, notifications, operations_log, wishlist, cart_items,
review_images, reviews, coupon_usage, user_coupons, coupons, shipping_companies, order_shipments,
order_payments, order_items, orders, warehouse_stock, warehouses, supplier_products, suppliers,
inventory, product_images, product_sku, products, categories, user_roles, roles, user_addresses,
user_profiles, users;

CREATE TABLE users (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(128),
    phone VARCHAR(32),
    status TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_users_username(username),
    KEY idx_users_phone(phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Users';

CREATE TABLE user_profiles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    avatar_url VARCHAR(255),
    bio TEXT,
    birthday DATE,
    gender VARCHAR(16),
    KEY idx_user_profiles_user_id(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User profile';

CREATE TABLE user_addresses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    province VARCHAR(64),
    city VARCHAR(64),
    detail_address VARCHAR(255),
    is_default TINYINT DEFAULT 0,
    KEY idx_user_addresses_user_id(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User addresses';

CREATE TABLE roles (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    role_name VARCHAR(64) NOT NULL,
    role_code VARCHAR(64) NOT NULL,
    UNIQUE KEY uk_roles_code(role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Roles';

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    KEY idx_user_roles_role_id(role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User role association';

CREATE TABLE categories (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    parent_id BIGINT,
    name VARCHAR(128) NOT NULL,
    sort_order INT DEFAULT 0,
    KEY idx_categories_parent_id(parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Categories';

CREATE TABLE products (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    category_id BIGINT NOT NULL,
    supplier_code VARCHAR(32),
    price DECIMAL(12,2) NOT NULL,
    status VARCHAR(16) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_products_category_id(category_id),
    KEY idx_products_supplier_code(supplier_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Products';

CREATE TABLE product_sku (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    sku_code VARCHAR(64) NOT NULL,
    spec_json JSON,
    price DECIMAL(12,2),
    KEY idx_product_sku_product_id(product_id),
    UNIQUE KEY uk_product_sku_code(sku_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Product SKU';

CREATE TABLE product_images (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    image_url VARCHAR(255),
    sort_order INT DEFAULT 0,
    KEY idx_product_images_product_id(product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Product images';

CREATE TABLE inventory (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id BIGINT NOT NULL,
    sku_id BIGINT,
    warehouse_id BIGINT,
    quantity INT DEFAULT 0,
    KEY idx_inventory_product_id(product_id),
    KEY idx_inventory_sku_id(sku_id),
    KEY idx_inventory_warehouse_id(warehouse_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Inventory';

CREATE TABLE suppliers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    supplier_code VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    contact_phone VARCHAR(32),
    UNIQUE KEY uk_suppliers_code(supplier_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Suppliers';

CREATE TABLE supplier_products (
    supplier_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    supplier_sku VARCHAR(64),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (supplier_id, product_id),
    KEY idx_supplier_products_product_id(product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Supplier products';

CREATE TABLE warehouses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    warehouse_code VARCHAR(32) NOT NULL,
    name VARCHAR(128),
    city VARCHAR(64),
    UNIQUE KEY uk_warehouses_code(warehouse_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Warehouses';

CREATE TABLE warehouse_stock (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku_id BIGINT,
    available_qty INT DEFAULT 0,
    locked_qty INT DEFAULT 0,
    KEY idx_warehouse_stock_warehouse_id(warehouse_id),
    KEY idx_warehouse_stock_product_id(product_id),
    KEY idx_warehouse_stock_sku_id(sku_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Warehouse stock';

CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    order_no VARCHAR(32) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending',
    total_amount DECIMAL(12,2),
    coupon_id BIGINT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_orders_order_no(order_no),
    KEY idx_orders_user_id(user_id),
    KEY idx_orders_coupon_id(coupon_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Orders';

CREATE TABLE order_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku_id BIGINT,
    quantity INT NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    KEY idx_order_items_order_id(order_id),
    KEY idx_order_items_product_id(product_id),
    KEY idx_order_items_sku_id(sku_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Order items';

CREATE TABLE order_payments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    payment_no VARCHAR(64),
    payment_method VARCHAR(32),
    amount DECIMAL(12,2),
    paid_at DATETIME,
    KEY idx_order_payments_order_id(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Order payments';

CREATE TABLE shipping_companies (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    company_code VARCHAR(32) NOT NULL,
    name VARCHAR(128) NOT NULL,
    hotline VARCHAR(32),
    UNIQUE KEY uk_shipping_company_code(company_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Shipping companies';

CREATE TABLE order_shipments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    shipping_company_id BIGINT NOT NULL,
    tracking_no VARCHAR(64),
    shipped_at DATETIME,
    KEY idx_order_shipments_order_id(order_id),
    KEY idx_order_shipments_shipping_company_id(shipping_company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Order shipments';

CREATE TABLE coupons (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    coupon_code VARCHAR(64) NOT NULL,
    title VARCHAR(128),
    discount_amount DECIMAL(12,2),
    valid_from DATETIME,
    valid_to DATETIME,
    UNIQUE KEY uk_coupons_code(coupon_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Coupons';

CREATE TABLE user_coupons (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    coupon_id BIGINT NOT NULL,
    status VARCHAR(16) DEFAULT 'unused',
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user_coupons_user_id(user_id),
    KEY idx_user_coupons_coupon_id(coupon_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User coupons';

CREATE TABLE coupon_usage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_coupon_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_coupon_usage_user_coupon_id(user_coupon_id),
    KEY idx_coupon_usage_order_id(order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Coupon usage';

CREATE TABLE reviews (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    order_item_id BIGINT,
    rating INT NOT NULL,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_reviews_user_id(user_id),
    KEY idx_reviews_product_id(product_id),
    KEY idx_reviews_order_item_id(order_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Reviews';

CREATE TABLE review_images (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id BIGINT NOT NULL,
    image_url VARCHAR(255),
    sort_order INT DEFAULT 0,
    KEY idx_review_images_review_id(review_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Review images';

CREATE TABLE cart_items (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    sku_id BIGINT,
    quantity INT DEFAULT 1,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_cart_items_user_id(user_id),
    KEY idx_cart_items_product_id(product_id),
    KEY idx_cart_items_sku_id(sku_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Cart items';

CREATE TABLE wishlist (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_wishlist_user_id(user_id),
    KEY idx_wishlist_product_id(product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Wishlist';

CREATE TABLE operations_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    operator_id BIGINT,
    operation_type VARCHAR(64),
    target_table VARCHAR(64),
    target_id BIGINT,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_operations_log_operator_id(operator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Operations log';

CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    title VARCHAR(128),
    content TEXT,
    read_flag TINYINT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    KEY idx_notifications_user_id(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Notifications';

CREATE TABLE sys_config (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(128) NOT NULL,
    config_value TEXT,
    description VARCHAR(255),
    UNIQUE KEY uk_sys_config_key(config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='System config';

CREATE TABLE data_dictionary (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dict_type VARCHAR(64) NOT NULL,
    dict_key VARCHAR(64) NOT NULL,
    dict_value VARCHAR(128),
    sort_order INT DEFAULT 0,
    KEY idx_data_dictionary_type(dict_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Data dictionary';
