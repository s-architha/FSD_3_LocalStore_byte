from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, Integer
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            sessionmaker, Session)

engine = create_engine("sqlite:///store.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, index=True)
    price: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String)
    image_url: Mapped[str] = mapped_column(String)
    stock: Mapped[int] = mapped_column(Integer)


class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    product_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)


Base.metadata.create_all(engine)

# ---------- Seed data (only when the table is empty) ----------
SEED = [
    ("Handmade Coconut Soap", "Home", 120, 25, "Natural coconut oil soap made by local artisans. Gentle on skin.", "soap"),
    ("Filter Coffee Powder 500g", "Food", 350, 10, "Freshly ground South Indian filter coffee, rich and aromatic.", "coffee"),
    ("Banana Chips 250g", "Food", 90, 40, "Crispy Kerala-style banana chips fried in coconut oil.", "chips"),
    ("Cotton Tote Bag", "Accessories", 199, 5, "Reusable cotton bag with a sturdy handle and roomy inside.", "totebag"),
    ("Brass Oil Lamp", "Home", 899, 0, "Traditional brass lamp, hand polished. Currently restocking.", "lamp"),
    ("Spice Gift Box", "Gifts", 499, 8, "Cardamom, pepper, cinnamon and cloves in a wooden box.", "spices"),
    ("Jackfruit Halwa 300g", "Food", 260, 15, "Slow cooked sweet made with ripe jackfruit and jaggery.", "halwa"),
    ("Coir Doormat", "Home", 275, 12, "Durable natural coir mat, woven locally.", "doormat"),
    ("Hand-painted Coaster Set", "Gifts", 340, 3, "Set of 4 wooden coasters with Kerala mural art.", "coasters"),
    ("Cold-pressed Coconut Oil 1L", "Food", 420, 20, "Pure virgin coconut oil, cold pressed in small batches.", "oil"),
    ("Jute Shopping Bag", "Accessories", 230, 18, "Strong eco-friendly jute bag with cotton lining.", "jute"),
    ("Sandalwood Incense Sticks", "Gifts", 150, 30, "Pack of 40 natural sandalwood incense sticks.", "incense"),
]

with SessionLocal() as db:
    if not db.query(Product).first():
        for name, cat, price, stock, desc, seed in SEED:
            db.add(Product(name=name, category=cat, price=price, stock=stock,
                           description=desc,
                           image_url=f"/image/{seed}"))
        db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_id(x_session_id: str = Header(min_length=8, max_length=64)) -> str:
    return x_session_id


class CartIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class QtyIn(BaseModel):
    quantity: int = Field(ge=1, le=99)


def product_dict(p: Product) -> dict:
    return {"id": p.id, "name": p.name, "category": p.category, "price": p.price,
            "description": p.description, "image_url": p.image_url,
            "stock": p.stock, "in_stock": p.stock > 0}


def cart_view(db: Session, sid: str) -> dict:
    items, total, count = [], 0.0, 0
    for ci in db.query(CartItem).filter_by(session_id=sid).order_by(CartItem.id).all():
        p = db.get(Product, ci.product_id)
        if not p:
            continue
        line = p.price * ci.quantity
        total += line
        count += ci.quantity
        items.append({"product_id": p.id, "name": p.name, "price": p.price,
                      "image_url": p.image_url, "stock": p.stock,
                      "quantity": ci.quantity, "line_total": line})
    return {"items": items, "total": total, "count": count}


VISUALS = {
    "soap": ("🧼", "#d1e7dd"), "coffee": ("☕", "#e8d5c4"),
    "chips": ("🍌", "#fff3cd"), "totebag": ("👜", "#cfe2ff"),
    "lamp": ("🪔", "#fde2c8"), "spices": ("🌶️", "#f8d7da"),
    "halwa": ("🍯", "#ffe5b4"), "doormat": ("🚪", "#e2d9c8"),
    "coasters": ("🎨", "#e0cffc"), "oil": ("🥥", "#e9f5e1"),
    "jute": ("🛍️", "#d3e4cd"), "incense": ("🕯️", "#f3e5f5"),
}


app = FastAPI(title="Local Store")


@app.get("/image/{key}", include_in_schema=False)
def product_image(key: str):
    emoji, color = VISUALS.get(key, ("🛍️", "#e9ecef"))
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='500' height='380' viewBox='0 0 500 380'>"
           f"<rect width='500' height='380' fill='{color}'/>"
           f"<text x='250' y='215' font-size='150' text-anchor='middle'>{emoji}</text></svg>")
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse("index.html")


@app.get("/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.query(Product.category).distinct().order_by(Product.category).all()
    return [r[0] for r in rows]


@app.get("/products")
def list_products(search: Optional[str] = None, category: Optional[str] = None,
                  sort: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Product)
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%"))
    if category and category != "All":
        q = q.filter(Product.category == category)
    if sort == "price_asc":
        q = q.order_by(Product.price.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price.desc())
    elif sort == "name":
        q = q.order_by(Product.name.asc())
    else:
        q = q.order_by(Product.id.asc())
    return [product_dict(p) for p in q.all()]


@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product_dict(p)


@app.get("/cart")
def get_cart(db: Session = Depends(get_db), sid: str = Depends(session_id)):
    return cart_view(db, sid)


@app.post("/cart/add", status_code=201)
def add_to_cart(data: CartIn, db: Session = Depends(get_db),
                sid: str = Depends(session_id)):
    p = db.get(Product, data.product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    if p.stock <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{p.name} is out of stock")
    item = db.query(CartItem).filter_by(session_id=sid, product_id=p.id).first()
    new_qty = (item.quantity if item else 0) + data.quantity
    if new_qty > p.stock:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Only {p.stock} of {p.name} available")
    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(session_id=sid, product_id=p.id, quantity=data.quantity))
    db.commit()
    return cart_view(db, sid)


@app.put("/cart/{product_id}")
def set_quantity(product_id: int, data: QtyIn, db: Session = Depends(get_db),
                 sid: str = Depends(session_id)):
    item = db.query(CartItem).filter_by(session_id=sid, product_id=product_id).first()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not in cart")
    p = db.get(Product, product_id)
    if data.quantity > p.stock:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Only {p.stock} of {p.name} available")
    item.quantity = data.quantity
    db.commit()
    return cart_view(db, sid)


@app.delete("/cart/{product_id}")
def remove_from_cart(product_id: int, db: Session = Depends(get_db),
                     sid: str = Depends(session_id)):
    item = db.query(CartItem).filter_by(session_id=sid, product_id=product_id).first()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not in cart")
    db.delete(item)
    db.commit()
    return cart_view(db, sid)


@app.delete("/cart")
def clear_cart(db: Session = Depends(get_db), sid: str = Depends(session_id)):
    db.query(CartItem).filter_by(session_id=sid).delete()
    db.commit()
    return cart_view(db, sid)