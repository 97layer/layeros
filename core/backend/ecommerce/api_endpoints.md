# WOOHWAHAE E-commerce API Endpoints

Base URL: `https://api.woohwahae.kr` (production) or `http://localhost:8000` (development)

API Version: `v1`

All endpoints prefixed with `/api/v1`

## Authentication

All authenticated endpoints require `Authorization: Bearer {token}` header.

### POST `/api/v1/auth/register`

Register new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "full_name": "홍길동",
  "phone": "010-1234-5678",
  "password": "securepassword123"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "홍길동",
  "phone": "010-1234-5678",
  "is_active": true,
  "is_verified": false,
  "is_admin": false,
  "created_at": "2026-02-28T12:00:00Z"
}
```

### POST `/api/v1/auth/login`

Login and receive JWT access token.

**Request Body:** (form-data)
```
username: user@example.com
password: securepassword123
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

### GET `/api/v1/auth/me`

Get current authenticated user information.

**Headers:** `Authorization: Bearer {token}`

**Response:** `200 OK`
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "홍길동",
  "phone": "010-1234-5678",
  "is_active": true,
  "is_verified": false,
  "is_admin": false,
  "created_at": "2026-02-28T12:00:00Z"
}
```

---

## Products

### GET `/api/v1/products`

List products with pagination and filters.

**Query Parameters:**
- `page` (int, default: 1) - Page number
- `page_size` (int, default: 20, max: 100) - Items per page
- `category` (string, optional) - Filter by category
- `is_published` (boolean, default: true) - Show only published
- `search` (string, optional) - Search in name/description

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "sku": "WH-HAIR-001",
      "name": "헤어 오일 30ml",
      "slug": "hair-oil-30ml",
      "description": "천연 성분 헤어 오일",
      "short_description": "자연에서 온 머릿결 케어",
      "price": "28000.00",
      "compare_at_price": "35000.00",
      "category": "hair-care",
      "tags": ["natural", "handmade"],
      "images": [
        {"url": "/images/products/hair-oil-01.jpg", "alt": "헤어 오일"}
      ],
      "stock_quantity": 50,
      "is_published": true,
      "is_featured": true,
      "is_in_stock": true,
      "is_low_stock": false,
      "created_at": "2026-02-28T12:00:00Z",
      "updated_at": "2026-02-28T12:00:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### GET `/api/v1/products/{product_id}`

Get product by ID.

**Response:** `200 OK`
```json
{
  "id": 1,
  "sku": "WH-HAIR-001",
  "name": "헤어 오일 30ml",
  "slug": "hair-oil-30ml",
  "price": "28000.00",
  "stock_quantity": 50,
  "is_in_stock": true,
  ...
}
```

### GET `/api/v1/products/slug/{slug}`

Get product by slug (URL-friendly identifier).

**Example:** `/api/v1/products/slug/hair-oil-30ml`

**Response:** `200 OK` (same as get by ID)

### POST `/api/v1/products` (Admin Only)

Create new product.

**Headers:** `Authorization: Bearer {admin_token}`

**Request Body:**
```json
{
  "sku": "WH-HAIR-002",
  "name": "헤어 밤 50ml",
  "slug": "hair-balm-50ml",
  "description": "자연에서 온 헤어 밤",
  "short_description": "촉촉한 머릿결을 위한",
  "price": "32000.00",
  "compare_at_price": "40000.00",
  "stock_quantity": 30,
  "category": "hair-care",
  "tags": ["natural", "moisturizing"],
  "images": [
    {"url": "/images/products/hair-balm-01.jpg", "alt": "헤어 밤"}
  ],
  "is_published": true,
  "track_inventory": true
}
```

**Response:** `201 Created`

### PATCH `/api/v1/products/{product_id}` (Admin Only)

Update product (partial update).

**Headers:** `Authorization: Bearer {admin_token}`

**Request Body:**
```json
{
  "price": "30000.00",
  "stock_quantity": 45,
  "is_featured": true
}
```

**Response:** `200 OK`

### DELETE `/api/v1/products/{product_id}` (Admin Only)

Delete product.

**Headers:** `Authorization: Bearer {admin_token}`

**Response:** `204 No Content`

---

## Cart

**Note:** All cart endpoints require `X-Session-ID` header for session management.

### GET `/api/v1/cart`

Get cart contents for current session.

**Headers:** `X-Session-ID: {session_uuid}`

**Response:** `200 OK`
```json
{
  "items": [
    {
      "product_id": 1,
      "product_name": "헤어 오일 30ml",
      "product_sku": "WH-HAIR-001",
      "product_image": "/images/products/hair-oil-01.jpg",
      "price": "28000.00",
      "quantity": 2,
      "subtotal": "56000.00"
    }
  ],
  "subtotal": "56000.00",
  "total_items": 1
}
```

### POST `/api/v1/cart/items`

Add item to cart.

**Headers:** `X-Session-ID: {session_uuid}`

**Request Body:**
```json
{
  "product_id": 1,
  "quantity": 2
}
```

**Response:** `201 Created`
```json
{
  "message": "Item added to cart"
}
```

### PATCH `/api/v1/cart/items/{product_id}`

Update cart item quantity.

**Headers:** `X-Session-ID: {session_uuid}`

**Request Body:**
```json
{
  "quantity": 3
}
```

**Note:** Set `quantity: 0` to remove item.

**Response:** `200 OK`

### DELETE `/api/v1/cart/items/{product_id}`

Remove item from cart.

**Headers:** `X-Session-ID: {session_uuid}`

**Response:** `204 No Content`

### DELETE `/api/v1/cart`

Clear entire cart.

**Headers:** `X-Session-ID: {session_uuid}`

**Response:** `204 No Content`

---

## Orders

### POST `/api/v1/orders`

Create new order from cart items.

**Headers:** `Authorization: Bearer {token}`

**Request Body:**
```json
{
  "items": [
    {
      "product_id": 1,
      "quantity": 2
    }
  ],
  "shipping_address": {
    "recipient_name": "홍길동",
    "phone": "010-1234-5678",
    "postal_code": "06035",
    "address_line1": "서울시 강남구 테헤란로 123",
    "address_line2": "456호",
    "city": "서울"
  },
  "shipping_method": "standard",
  "payment_method": "tosspayments",
  "customer_note": "문 앞에 놓아주세요"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "order_number": "WH20260228120000",
  "user_id": 1,
  "status": "pending",
  "payment_status": "pending",
  "subtotal": "56000.00",
  "shipping_fee": "0.00",
  "discount_amount": "0.00",
  "total": "56000.00",
  "shipping_address": {
    "recipient_name": "홍길동",
    "phone": "010-1234-5678",
    "postal_code": "06035",
    "address_line1": "서울시 강남구 테헤란로 123",
    "address_line2": "456호",
    "city": "서울"
  },
  "shipping_method": "standard",
  "tracking_number": null,
  "payment_method": "tosspayments",
  "customer_note": "문 앞에 놓아주세요",
  "created_at": "2026-02-28T12:00:00Z",
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "product_name": "헤어 오일 30ml",
      "product_sku": "WH-HAIR-001",
      "product_image": "/images/products/hair-oil-01.jpg",
      "unit_price": "28000.00",
      "quantity": 2,
      "subtotal": "56000.00"
    }
  ]
}
```

### GET `/api/v1/orders`

List user's orders with pagination.

**Headers:** `Authorization: Bearer {token}`

**Query Parameters:**
- `page` (int, default: 1)
- `page_size` (int, default: 20, max: 100)
- `status` (string, optional) - Filter by order status

**Response:** `200 OK`
```json
{
  "items": [/* array of orders */],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### GET `/api/v1/orders/{order_id}`

Get order details.

**Headers:** `Authorization: Bearer {token}`

**Response:** `200 OK` (same format as create order response)

### PATCH `/api/v1/orders/{order_id}` (Admin Only)

Update order status.

**Headers:** `Authorization: Bearer {admin_token}`

**Request Body:**
```json
{
  "status": "shipped",
  "payment_status": "paid",
  "tracking_number": "CJ1234567890",
  "admin_note": "배송 완료"
}
```

**Response:** `200 OK`

### DELETE `/api/v1/orders/{order_id}`

Cancel order (only pending/confirmed orders).

**Headers:** `Authorization: Bearer {token}`

**Response:** `204 No Content`

---

## Order Status Flow

```
pending → confirmed → processing → shipped → delivered
         ↓
      cancelled
```

## Payment Status

- `pending` - Awaiting payment
- `paid` - Payment successful
- `failed` - Payment failed
- `refunded` - Payment refunded

---

## Error Responses

All endpoints return consistent error format:

**400 Bad Request:**
```json
{
  "detail": "Invalid request data"
}
```

**401 Unauthorized:**
```json
{
  "detail": "Could not validate credentials"
}
```

**403 Forbidden:**
```json
{
  "detail": "Admin privileges required"
}
```

**404 Not Found:**
```json
{
  "detail": "Product not found"
}
```

**422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

---

## Rate Limiting (To Be Implemented)

Recommended limits:
- Anonymous: 100 requests/hour
- Authenticated: 1000 requests/hour
- Admin: Unlimited

---

## Webhooks (To Be Implemented)

Payment gateway webhooks for order confirmation:
- `/webhooks/stripe` - Stripe payment events
- `/webhooks/tosspayments` - TossPayments callbacks
