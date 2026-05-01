from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity
)
import mercadopago
from flask_sqlalchemy import SQLAlchemy
import os
from email_validator import validate_email, EmailNotValidError

app = Flask(__name__)
CORS(app)

# 🔐 JWT
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret")
jwt = JWTManager(app)

# 💳 MercadoPago (CAMBIAR POR TU TOKEN REAL)
sdk = mercadopago.SDK(os.getenv("MP_ACCESS_TOKEN", "TU_ACCESS_TOKEN"))

# 🔌 PostgreSQL (Render)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL",
    "postgresql://usuario:password@host/ecommerce_db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# 📦 MODELOS
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    producto = db.Column(db.String(200), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    direccion = db.Column(db.String(200), nullable=False)
    total = db.Column(db.Integer, nullable=False)

# 🏠 HOME
@app.route("/")
def home():
    return jsonify({"msg": "API PRO funcionando con pagos"})

# 🛠 INIT DB
@app.route("/init")
def init():
    db.create_all()
    return jsonify({"msg": "DB lista"})

# 👤 REGISTER
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    nombre = data.get("name")
    email = data.get("email")
    username = data.get("username")
    password = data.get("password")

    if not nombre or not email or not username or not password:
        return jsonify({"error": "Faltan datos"}), 400

    try:
        validate_email(email)
    except EmailNotValidError:
        return jsonify({"error": "Email inválido"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Usuario ya existe"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email ya registrado"}), 400

    hashed_pw = generate_password_hash(password)
    user = User(nombre=nombre, email=email, username=username, password=hashed_pw)

    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "Usuario creado"}), 201

# 🔑 LOGIN
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = User.query.filter_by(username=data["username"]).first()

    if user and check_password_hash(user.password, data["password"]):
        token = create_access_token(identity=user.id)
        return jsonify({"token": token})
    return jsonify({"error": "Credenciales incorrectas"}), 401

# 🔒 PERFIL
@app.route("/perfil")
@jwt_required()
def perfil():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return jsonify({
        "nombre": user.nombre,
        "email": user.email,
        "username": user.username
    })

# 📦 PRODUCTOS
@app.route("/products", methods=["GET"])
def get_products():
    products = Product.query.all()
    return jsonify([{"id": p.id, "name": p.name, "price": p.price} for p in products])

@app.route("/products", methods=["POST"])
@jwt_required()
def add_product():
    data = request.json
    product = Product(name=data["name"], price=data["price"])
    db.session.add(product)
    db.session.commit()
    return jsonify({"msg": "Producto agregado"})

# 🛒 CARRITO
@app.route("/cart", methods=["POST"])
@jwt_required()
def add_to_cart():
    user_id = get_jwt_identity()
    data = request.json
    cart_item = Cart(user_id=user_id, product_id=data["product_id"])
    db.session.add(cart_item)
    db.session.commit()
    return jsonify({"msg": "Agregado al carrito"})

@app.route("/cart", methods=["GET"])
@jwt_required()
def get_cart():
    user_id = get_jwt_identity()
    items = db.session.query(Product).join(Cart, Product.id == Cart.product_id).filter(Cart.user_id == user_id).all()
    total = sum(p.price for p in items)
    return jsonify({
        "items": [{"id": p.id, "name": p.name, "price": p.price} for p in items],
        "total": total
    })

# 📦 CHECKOUT
@app.route("/checkout", methods=["POST"])
@jwt_required()
def checkout():
    user_id = get_jwt_identity()
    items = db.session.query(Product).join(Cart, Product.id == Cart.product_id).filter(Cart.user_id == user_id).all()
    total = sum(p.price for p in items)

    # Guardar orden simple
    order = Order(user_id=user_id, producto="Carrito completo", precio=total,
                  nombre="N/A", email="N/A", direccion="N/A", total=total)
    db.session.add(order)
    Cart.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    return jsonify({"msg": "Compra realizada", "total": total})

# 💳 MERCADOPAGO con datos del comprador
@app.route("/create_preference", methods=["POST"])
@jwt_required()
def create_preference():
    user_id = get_jwt_identity()
    data = request.json

    title = data.get("title")
    price = data.get("price")
    buyer = data.get("buyer", {})
    nombre = buyer.get("nombre")
    email = buyer.get("email")
    direccion = buyer.get("direccion")

    # Guardar orden detallada
    nueva_orden = Order(user_id=user_id, producto=title, precio=price,
                        nombre=nombre, email=email, direccion=direccion, total=price)
    db.session.add(nueva_orden)
    db.session.commit()

    preference_data = {
        "items": [
            {
                "title": title,
                "quantity": 1,
                "currency_id": "ARS",
                "unit_price": float(price)
            }
        ],
        "payer": {
            "name": nombre,
            "email": email,
            "address": {
                "street_name": direccion
            }
        },
        "back_urls": {
            "success": "https://tu-sitio.com/success",
            "failure": "https://tu-sitio.com/failure",
            "pending": "https://tu-sitio.com/pending"
        },
        "auto_return": "approved"
    }

    preference = sdk.preference().create(preference_data)
    return jsonify({"init_point": preference["response"]["init_point"]})

# 📜 LISTAR ÓRDENES
@app.route("/orders", methods=["GET"])
@jwt_required()
def get_orders():
    user_id = get_jwt_identity()
    orders = Order.query.filter_by(user_id=user_id).all()
    return jsonify([
        {
            "id": o.id,
            "producto": o.producto,
            "precio": o.precio,
            "nombre": o.nombre,
            "email": o.email,
            "direccion": o.direccion,
            "total": o.total
        } for o in orders
    ])


# ▶️ RUN
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=False, use_reloader=False)
