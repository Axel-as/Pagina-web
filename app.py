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

app = Flask(__name__)
CORS(app)

# 🔐 JWT
app.config["JWT_SECRET_KEY"] = "super-secret"
jwt = JWTManager(app)

# 💳 MercadoPago (CAMBIAR POR TU TOKEN REAL)
sdk = mercadopago.SDK("TU_ACCESS_TOKEN")

# 🔌 PostgreSQL (Render)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL",
    "postgresql://ecommerce_db_p18r_user:t5ZMxyWVHMegML2gsbuWYg4dqH3MWzZI@dpg-d7q0ekfavr4c73fd0ll0-a.virginia-postgres.render.com/ecommerce_db_p18r")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# 📦 MODELOS
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    hashed_pw = generate_password_hash(data["password"])
    user = User(username=data["username"], password=hashed_pw)

    try:
        db.session.add(user)
        db.session.commit()
    except:
        return jsonify({"error": "Usuario ya existe"}), 400

    return jsonify({"msg": "Usuario creado"})

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
    return jsonify({"msg": f"Usuario {user_id} autenticado"})

# 📦 PRODUCTOS
@app.route("/products", methods=["GET"])
def get_products():
    products = Product.query.all()
    return jsonify([{"id": p.id, "name": p.name, "price": p.price} for p in products])

# ➕ AGREGAR PRODUCTO
@app.route("/products", methods=["POST"])
@jwt_required()
def add_product():
    data = request.json
    product = Product(name=data["name"], price=data["price"])
    db.session.add(product)
    db.session.commit()
    return jsonify({"msg": "Producto agregado"})

# 🛒 AGREGAR AL CARRITO
@app.route("/cart", methods=["POST"])
@jwt_required()
def add_to_cart():
    user_id = get_jwt_identity()
    data = request.json
    cart_item = Cart(user_id=user_id, product_id=data["product_id"])
    db.session.add(cart_item)
    db.session.commit()
    return jsonify({"msg": "Agregado al carrito"})

# 📦 VER CARRITO
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

# 📦 CHECKOUT (pedido)
@app.route("/checkout", methods=["POST"])
@jwt_required()
def checkout():
    user_id = get_jwt_identity()
    items = db.session.query(Product).join(Cart, Product.id == Cart.product_id).filter(Cart.user_id == user_id).all()
    total = sum(p.price for p in items)

    order = Order(user_id=user_id, total=total)
    db.session.add(order)
    Cart.query.filter_by(user_id=user_id).delete()
    db.session.commit()

    return jsonify({"msg": "Compra realizada", "total": total})

# 💳 CREAR PREFERENCIA DE PAGO (MercadoPago)
@app.route("/create_preference", methods=["POST"])
@jwt_required()
def create_preference():
    data = request.json
    preference_data = {
        "items": [
            {
                "title": data["title"],
                "quantity": 1,
                "unit_price": data["price"]
            }
        ]
    }
    preference = sdk.preference().create(preference_data)
    return jsonify({"init_point": preference["response"]["init_point"]})

# ▶️ RUN
if __name__ == "__main__":
    app.run(debug=False, use_reloader=False)
