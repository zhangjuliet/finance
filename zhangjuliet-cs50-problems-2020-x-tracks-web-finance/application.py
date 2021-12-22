import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
    stocks = db.execute("SELECT symbol, price, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])
    quotes = {}
    grand_total = 0.0

    # Iterate through stocks
    for stock in stocks:
        quotes[stock["symbol"]] = lookup(stock["symbol"])

    # Add total value of each holding to grand total
    for i in range(len(stocks)):
        grand_total += float(stocks[i]["total_shares"] * stocks[i]["price"])

    # Add cash left to grand total
    cash_left = user[0]["cash"]
    grand_total += float(cash_left)
    return render_template("portfolio.html", quotes=quotes, stocks=stocks, cash_left=usd(cash_left), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol")

        stock = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")

        # Ensure submitted symbol is valid
        if not stock:
            return apology("invalid symbol")

        # Ensure positive number of shares was submitted
        if not shares:
            return apology("missing shares")
        elif int(shares) < 1:
            return apology("invalid shares")

        user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=session["user_id"])
        funds = user[0]["cash"]
        total_price = stock["price"] * float(shares)

        # Ensure that user can afford the number of shares at the current price
        if funds < total_price:
            return apology("cannot afford shares")

        # Update users and transactions tables
        db.execute("UPDATE users SET cash = cash - :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=shares, price=stock["price"])

        flash("Bought!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY transacted ASC", user_id=session["user_id"])
    return render_template("history.html", transactions=transactions)

@app.route("/add_cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Allow user to add additional cash to their account"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        amount = float(request.form.get("amount"))

        # Ensure amount of cash was submitted
        if not amount:
            return apology("invalid amount")

        # Update user's cash
        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id", user_id=session["user_id"], amount=amount)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("add_cash.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol")

        # Returns stock name, price, and symbol
        stock = lookup(request.form.get("symbol"))

        # Ensure submitted symbol is valid
        if not stock:
            return apology("invalid symbol")

        # Redirect user to quoted page
        return render_template("quoted.html", name=stock["name"], symbol=stock["symbol"], price=usd(stock["price"]))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 403)

        # Query database for username and ensure username does not already exist
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        if len(rows) >= 1:
            return apology("username already exists", 403)

        # Add user to database and remember session
        primary_key = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))
        session["user_id"] = primary_key

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    stocks = db.execute("SELECT * FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING SUM(shares) > 0", user_id=session["user_id"])

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("missing symbol")

        # Ensure positive number of shares was submitted
        shares = request.form.get("shares")
        if not shares:
            return apology("missing shares")
        elif int(shares) < 1:
            return apology("invalid shares")

        # Check if user has enough shares to sell
        stock = db.execute("SELECT SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
                            user_id=session["user_id"], symbol=request.form.get("symbol"))
        if len(stock) == 0:
            return apology("no shares owned")
        elif stock[0]["total_shares"] < int(shares):
            return apology("cannot sell more shares than owned")

        total_price = quote["price"] * float(shares)

        # Update users and transactions tables
        db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price=total_price, user_id=session["user_id"])
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                    user_id=session["user_id"], symbol=request.form.get("symbol"), shares=int(shares)*-1, price=quote["price"])

        flash("Sold!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
