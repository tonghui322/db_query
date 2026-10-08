-- ============================================================
-- 示例数据库：简易电商订单库（用于 demo 试效果）
-- 在 MySQL 里执行本脚本，然后 .env 里 DB_NAME=nl2sql_demo
-- ============================================================

CREATE DATABASE IF NOT EXISTS nl2sql_demo DEFAULT CHARACTER SET utf8mb4;
USE nl2sql_demo;

-- 用户表
CREATE TABLE IF NOT EXISTS customers (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    name VARCHAR(50) NOT NULL COMMENT '用户姓名',
    gender ENUM('男','女') COMMENT '性别',
    age INT COMMENT '年龄',
    city VARCHAR(50) COMMENT '所在城市',
    register_date DATE COMMENT '注册日期',
    vip_level INT DEFAULT 0 COMMENT '会员等级(0普通/1银/2金/3钻)'
) COMMENT='用户信息表';

-- 商品表
CREATE TABLE IF NOT EXISTS products (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '商品ID',
    name VARCHAR(100) NOT NULL COMMENT '商品名称',
    category VARCHAR(50) COMMENT '商品分类',
    price DECIMAL(10,2) COMMENT '单价(元)',
    stock INT DEFAULT 0 COMMENT '库存数量'
) COMMENT='商品信息表';

-- 订单表
CREATE TABLE IF NOT EXISTS orders (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '订单ID',
    customer_id INT NOT NULL COMMENT '下单用户ID(关联customers.id)',
    order_date DATETIME COMMENT '下单时间',
    total_amount DECIMAL(10,2) COMMENT '订单总金额(元)',
    status VARCHAR(20) COMMENT '订单状态(已支付/未支付/已取消/已发货/已完成)',
    FOREIGN KEY (customer_id) REFERENCES customers(id)
) COMMENT='订单表';

-- 订单明细表
CREATE TABLE IF NOT EXISTS order_items (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '明细ID',
    order_id INT NOT NULL COMMENT '所属订单ID(关联orders.id)',
    product_id INT NOT NULL COMMENT '商品ID(关联products.id)',
    quantity INT COMMENT '购买数量',
    price DECIMAL(10,2) COMMENT '成交单价(元)',
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
) COMMENT='订单明细表';

-- ============ 造数 ============
INSERT INTO customers (name, gender, age, city, register_date, vip_level) VALUES
('张三','男',28,'北京','2024-01-15',2),
('李四','女',32,'上海','2024-02-20',1),
('王五','男',45,'广州','2023-11-05',3),
('赵六','女',24,'深圳','2024-05-18',0),
('孙七','男',38,'北京','2023-08-12',1),
('周八','女',29,'杭州','2024-03-30',2);

INSERT INTO products (name, category, price, stock) VALUES
('iPhone 15', '手机', 5999.00, 120),
('小米14', '手机', 3999.00, 300),
('华为 Mate60', '手机', 6499.00, 80),
('MacBook Air', '笔记本', 7999.00, 50),
('联想小新', '笔记本', 4599.00, 200),
('机械键盘', '外设', 499.00, 500),
('无线鼠标', '外设', 99.00, 800);

INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
(1,'2024-06-01 10:00:00',5999.00,'已完成'),
(1,'2024-06-15 14:30:00',499.00,'已发货'),
(2,'2024-06-02 09:00:00',7999.00,'已完成'),
(3,'2024-06-05 20:00:00',6499.00,'已支付'),
(4,'2024-06-10 11:00:00',4098.00,'已完成'),
(5,'2024-06-12 16:00:00',4599.00,'已取消'),
(6,'2024-06-20 10:30:00',99.00,'已支付');

INSERT INTO order_items (order_id, product_id, quantity, price) VALUES
(1,1,1,5999.00),
(2,6,1,499.00),
(3,4,1,7999.00),
(4,3,1,6499.00),
(5,2,1,3999.00),
(5,7,1,99.00),
(6,7,1,99.00);
