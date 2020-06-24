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

    # Do not show any stocks if you don't own any shares
    db.execute("DELETE FROM portfolios WHERE shares=:shares", shares=0)

    # Get current user's id
    currentid = session["user_id"]

    # Get user's portfolios
    rows = db.execute("SELECT * FROM portfolios WHERE id = :currentid", currentid=currentid)
    all_stocks = []

    # Get current user's  cash
    totalCash1 = db.execute("SELECT cash FROM users WHERE id=:idd", idd=session["user_id"])
    totalCash = totalCash1[0]["cash"]
    grandTotal = totalCash

    for i in range(len(rows)):
        symbol = rows[i]["symbol"]

        # perform lookup function on symbol
        nameLookup = lookup(symbol)

        name = nameLookup["name"]
        currPrice = nameLookup["price"]
        shares = rows[i]["shares"]
        totalStock = shares * currPrice
        grandTotal += totalStock

        all_stocks.append({"symbol": symbol, "name": name, "shares": shares, "currPrice": usd(currPrice), "totalStock": usd(totalStock)})

    length = len(all_stocks)
    return render_template("index.html", all_stocks=all_stocks, totalCash=usd(totalCash), grandTotal=usd(grandTotal), length=length)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        result = lookup(request.form.get("symbol"))

        # Checks if symbol is valid
        if result == None:
            return apology("This symbol does not exist")

        numShares = float(request.form.get("shares"))

        # Check if number of shares is positive
        if not numShares > 0:
            return apology("Number of shares must be positive")

        # Get user's cash amount
        cashdictlist = db.execute("SELECT cash FROM users WHERE id = :idd", idd=session["user_id"])
        cash = cashdictlist[0]["cash"]

        # Check if user has enough money to purchase stocks
        if cash - numShares * result["price"] < 0:
            return apology("you do not have enough cash")

        db.execute("INSERT INTO purchases (id, shares, price, name) VALUES (?, ?, ?, ?)",
                   session["user_id"], numShares, result["price"], result["symbol"])

        # cash after subtracting price of stocks
        newcash = cash - result["price"] * numShares

        # update users cash in user table
        db.execute("UPDATE users SET cash=:newcash WHERE id=:idd",
                        idd=session["user_id"], newcash=newcash)

        # Get user's portfolio
        portfolio = db.execute("SELECT shares FROM portfolios WHERE id = :user_id AND symbol = :symbol",
                user_id = session["user_id"],
                symbol = result["symbol"])

        # Update portfolios table
        if len(portfolio) > 0:
            shares = numShares + portfolio[0]["shares"]

            db.execute("UPDATE portfolios SET shares=:shares WHERE id=:idd AND symbol=:symbol",
                        idd=session["user_id"], shares=shares, symbol=result["symbol"])

        else:
            db.execute("INSERT INTO portfolios (id, shares, symbol) VALUES (?,?,?)",
                        session["user_id"], numShares, result["symbol"])

        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    db.execute("DELETE FROM history")

    Pur = db.execute("SELECT * FROM purchases WHERE id=:idd", idd=session["user_id"])
    Sal = db.execute("SELECT * FROM sales WHERE id=:idd", idd=session["user_id"])

    lengthPur = len(Pur)
    lengthSal = len(Sal)

    for i in range(lengthPur):
        db.execute("INSERT INTO history (symbol, shares, price, time) VALUES (?,?,?,?)",
                    Pur[i]["name"], Pur[i]["shares"], usd(Pur[i]["price"]), Pur[i]["time"])

    for i in range(lengthSal):
        db.execute("INSERT INTO history (symbol, shares, price, time) VALUES (?,?,?,?)",
                    Sal[i]["name"], Sal[i]["shares"], usd(Sal[i]["price"]), Sal[i]["time"])

    history = db.execute("SELECT * FROM history ORDER BY time DESC")

    length = len(history)

    return render_template("history.html", length=length, history=history)


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

    if request.method == "GET":
        return render_template("quote.html")

    else:
        result = lookup(request.form.get("symbol"))

        # Checks if symbol is valid
        if (result == None):
            return apology("This symbol does not exist")

        # Get properties of result
        stockName = result["name"]
        stockPrice = usd(result["price"])
        stockSymbol = result["symbol"]

        # Renders quoted.html
        return render_template("quoted.html", stockName=stockName, stockPrice=stockPrice, stockSymbol=stockSymbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")

    else:
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        #Ensure confirm password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password", 403)

        #Ensure confirm password == password
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords do not match")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Check if username is already taken
        if len(rows) >= 1:
            return apology("username already taken")

        # Hash password and insert into db
        hashedpwd = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), hashedpwd)
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":
        portfolio = db.execute("SELECT * FROM portfolios WHERE id=:idd", idd=session["user_id"])
        length = len(portfolio)

        return render_template("sell.html", portfolio=portfolio, length=length)

    else:
        stockSymbol = request.form.get("symbol")
        stockShares = float(request.form.get("shares"))
        result = lookup(stockSymbol)

        # Query database for number of shares that user "id" has for symbol "symbol"
        portfolio = db.execute("SELECT shares FROM portfolios WHERE id=:idd AND symbol=:symbol",
                                idd=session["user_id"], symbol=stockSymbol)

        # Check if you have enough shares to sell or if stockShares is negative
        if stockShares < 0 or stockShares > portfolio[0]["shares"]:
            return apology("You do not have that many shares")

        # Check if user fails to select a stock
        if not stockSymbol:
            return apology("You did not select a stock symbol to sell")

        # Check if user tries to sell 0 shares
        if stockShares == 0:
            return apology("You cannot sell 0 shares")

        # Get user's cash amount
        cash = db.execute("SELECT cash FROM users WHERE id = :idd", idd=session["user_id"])[0]["cash"]

        # user's additional cash after selling stock
        newcash = cash + float(result["price"]) * stockShares

        # Update user's money
        db.execute("UPDATE users SET cash=:newcash WHERE id=:idd", idd=session["user_id"], newcash=newcash)

        # Add sale into sales table
        db.execute("INSERT INTO sales (id, shares, price, name) VALUES (?,?,?,?)",
                    session["user_id"], (stockShares * -1), float(result["price"]), stockSymbol)

        # Update portfolios table
        if len(portfolio) > 0:
            shares = portfolio[0]["shares"] - stockShares

            db.execute("UPDATE portfolios SET shares=:shares WHERE id=:idd AND symbol=:symbol",
                        idd=session["user_id"], shares=shares, symbol=result["symbol"])

        return redirect("/")


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    """ Deposit more cash into user account """

    if request.method == "GET":
        return render_template("deposit.html")

    else:
        # Check if something was actually inputted
        if not request.form.get("amount"):
            return apology("Please input something")

        else:
            depositAmt = float(request.form.get("amount"))

        # Check if amt is positive and not zero
        if not depositAmt > 0:
            return apology("Please input a positive number you would like to deposit")

        # Add deposit amount to user's cash in db
        db.execute("UPDATE users SET cash = cash + :depositAmt WHERE id=:idd", idd=session["user_id"], depositAmt=depositAmt)

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
