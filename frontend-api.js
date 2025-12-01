// frontend-api.js
const BACKEND = "https://your-backend.onrender.com"; // <-- set this after Render deploy

async function loadMenuToDOM(renderFn){
  const r = await fetch(BACKEND + "/api/menu");
  const items = await r.json();
  renderFn(items);
}

// Simple cart (keeps in localStorage so page refresh keeps cart)
const CART_KEY = "sr_cart_v1";
function getCart(){ return JSON.parse(localStorage.getItem(CART_KEY) || "[]"); }
function saveCart(c){ localStorage.setItem(CART_KEY, JSON.stringify(c)); }
function addToCart(item){
  let cart = getCart();
  let found = cart.find(i=>i.id===item.id);
  if(found){ found.qty += 1; } else { cart.push({...item, qty:1}); }
  saveCart(cart);
  updateCartBadge();
}
function removeFromCart(itemId){
  let cart = getCart().filter(i=> i.id !== itemId);
  saveCart(cart);
  updateCartBadge();
}
function updateQty(itemId, qty){
  let cart = getCart();
  cart = cart.map(i => i.id===itemId ? {...i, qty: qty} : i).filter(i => i.qty>0);
  saveCart(cart);
  updateCartBadge();
}
function clearCart(){ localStorage.removeItem(CART_KEY); updateCartBadge(); }

function updateCartBadge(){
  const cart = getCart();
  let count = cart.reduce((s,i)=> s + (i.qty||0), 0);
  document.getElementById("cart-items").innerText = count;
  document.getElementById("cart-total").innerText = cart.reduce((s,i)=> s + i.price*(i.qty||1),0).toFixed(2);
}

// Place order -> create DB order -> create Razorpay order -> open checkout -> verify
async function placeOrderFlow(tableNo){
  const cart = getCart();
  if(cart.length===0){ alert("Cart empty"); return; }
  // 1) create local order
  const orderResp = await fetch(BACKEND + "/api/order", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({table_no: tableNo, items: cart})
  });
  const orderData = await orderResp.json();
  if(orderResp.status !== 201){ alert("Order failed: "+(orderData.error||JSON.stringify(orderData))); return; }
  const localOrderId = orderData.order_id;
  const total = orderData.total;

  // 2) create Razorpay order on server
  const r = await fetch(BACKEND + "/api/create_razorpay_order", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({amount: total, currency:"INR", receipt:"rcpt_"+localOrderId, order_id: localOrderId})
  });
  const rdata = await r.json();
  if(rdata.error){ alert("Payment init error: "+rdata.error); return; }

  // 3) Open Razorpay checkout
  const options = {
    "key": "{{RAZORPAY_KEY_ID}}", // replace in your hosted page with actual public key string or set dynamically from config
    "amount": rdata.amount,
    "currency": rdata.currency,
    "order_id": rdata.id,
    "name": "Smart Restaurant",
    "description": "Order Payment",
    "handler": async function(response){
      // verify server-side
      const verify = await fetch(BACKEND + "/api/razorpay_success", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_order_id: response.razorpay_order_id,
          razorpay_signature: response.razorpay_signature,
          local_order_id: localOrderId
        })
      });
      const v = await verify.json();
      if(v.status === 'success'){ clearCart(); alert("Payment success! Order ID: " + localOrderId); }
      else { alert("Payment verification failed"); }
    }
  };
  const rzp = new Razorpay(options);
  rzp.open();
}