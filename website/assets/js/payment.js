/**
 * WOOHWAHAE 토스페이먼츠 결제 모듈
 * 백엔드 없이 프론트엔드에서 직접 결제 처리
 */

// 토스페이먼츠 클라이언트 키 (실제 운영 시 환경변수로 관리)
const TOSS_CLIENT_KEY = 'test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq'; // 테스트 키

// 상품 정보
const PRODUCTS = {
  workbook_digital: {
    name: '영점의 발견 Workbook — Digital PDF',
    price: 15000,
    description: '브랜드 정렬을 위한 30개 질문 + 리플렉션 여백 페이지.'
  },
  workbook_riso: {
    name: '영점의 발견 Workbook — Riso Print',
    price: 35000,
    description: '리소 인쇄본 + 가이드 카드 세트 (배송 상품).'
  },
  photography: {
    name: 'Snap Photography',
    price: 200000,
    description: '과장 없이 당신의 표정과 공기를 기록. 원본 및 보정본 10매 제공.'
  },
  manual_pdf: {
    name: 'Atelier Manual PDF',
    price: 85000,
    description: '1인 미용실 생존 가이드라인 전자책.'
  },
  incense: {
    name: 'Signature Incense',
    price: 32000,
    description: '우화해 공간의 향. 샌달우드와 베티버 베이스.'
  },
  slow_object_001: {
    name: 'Slow Object Report #001 — 가위',
    price: 28000,
    description: '도구의 본질에 대한 탐구. Magazine B 스타일 오브제 해부 전자책.'
  }
};

const FX_REFERENCE_KRW_PER_USD = 1350;

function isEnglishSession() {
  const params = new URLSearchParams(window.location.search);
  const langParam = String(params.get('lang') || '').toLowerCase();
  if (langParam === 'en') return true;
  if (langParam === 'ko') return false;
  return !String(navigator.language || 'en').toLowerCase().startsWith('ko');
}

function formatKRW(amount) {
  return new Intl.NumberFormat('ko-KR').format(amount);
}

function estimateUSD(amountKRW) {
  const estimated = Math.round((amountKRW / FX_REFERENCE_KRW_PER_USD) * 10) / 10;
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 1 }).format(estimated);
}

function resolveProductIdFromOrder(orderId) {
  if (!orderId) return null;
  const knownIds = Object.keys(PRODUCTS).sort((a, b) => b.length - a.length);
  for (const key of knownIds) {
    if (orderId.endsWith(`_${key}`) || orderId === key) {
      return key;
    }
  }
  const parts = orderId.split('_');
  if (parts.length > 2) {
    return parts.slice(2).join('_');
  }
  return null;
}

/**
 * 토스페이먼츠 결제 시작
 * @param {string} productId - 상품 ID
 * @param {number} amount - 결제 금액
 * @param {object} options - 선택 옵션
 */
function initTossPayment(productId, amount, options = {}) {
  const product = PRODUCTS[productId];

  if (!product) {
    alert('상품 정보를 찾을 수 없습니다.');
    return;
  }

  const requestedAmount = Number(amount);
  const paymentAmount = Number.isFinite(requestedAmount) && requestedAmount > 0
    ? requestedAmount
    : product.price;

  const externalOrderNumber = String(options.orderNumber || '').trim();
  const normalizedOrderNumber = externalOrderNumber
    ? externalOrderNumber.replace(/[^A-Za-z0-9-]/g, '')
    : '';

  // 주문 ID 생성 (타임스탬프 기반)
  const orderId = normalizedOrderNumber
    ? `ORDER_${normalizedOrderNumber}_${productId}`
    : `ORDER_${Date.now()}_${productId}`;

  // 결제 요청 데이터
  const paymentData = {
    amount: paymentAmount,
    orderId: orderId,
    orderName: product.name,
    customerName: String(options.customerName || (isEnglishSession() ? 'Customer' : '구매자')),
    successUrl: `${window.location.origin}/payment-success.html`,
    failUrl: `${window.location.origin}/payment-fail.html`,
  };

  // 토스페이먼츠 SDK 로드 후 결제창 호출
  if (typeof TossPayments === 'undefined') {
    alert('결제 모듈 로딩 중입니다. 잠시 후 다시 시도해주세요.');
    return;
  }

  const tossPayments = TossPayments(TOSS_CLIENT_KEY);

  tossPayments.requestPayment('카드', paymentData)
    .catch(function (error) {
      if (error.code === 'USER_CANCEL') {
        console.log('결제 취소');
      } else {
        console.error('결제 오류:', error);
        alert('결제 중 오류가 발생했습니다.');
      }
    });
}

/**
 * 결제 성공 처리 (success.html에서 호출)
 */
function handlePaymentSuccess() {
  const isEnglish = isEnglishSession();
  const urlParams = new URLSearchParams(window.location.search);
  const orderId = urlParams.get('orderId');
  const amount = urlParams.get('amount');
  const paymentKey = urlParams.get('paymentKey');

  // 실제로는 백엔드로 전송해 승인 처리해야 하지만,
  // 백엔드 없이 프론트엔드만으로 처리하는 경우 제한적
  console.log('결제 성공:', { orderId, amount, paymentKey });

  const productId = resolveProductIdFromOrder(orderId);

  const statusLead = document.getElementById('status-lead');
  if (statusLead) {
    statusLead.textContent = isEnglish ? 'Payment completed.' : '결제가 완료되었습니다.';
  }

  const statusNote = document.getElementById('status-note');
  if (statusNote) {
    statusNote.innerHTML = isEnglish
      ? 'A confirmation email will be sent shortly.<br>If you need help, contact hello@woohwahae.kr.'
      : '구매하신 상품은 등록하신 이메일로도 전송됩니다.<br>문의사항은 hello@woohwahae.kr로 연락 주세요.';
  }

  const statusCta = document.getElementById('status-cta');
  if (statusCta) {
    statusCta.textContent = isEnglish ? 'Back to Practice →' : 'Practice로 돌아가기 →';
  }

  const orderInfo = document.getElementById('order-info');
  if (orderInfo) {
    const numericAmount = Number(amount);
    if (orderId && Number.isFinite(numericAmount) && numericAmount > 0) {
      orderInfo.textContent = isEnglish
        ? `Order ${orderId} confirmed · KRW ${formatKRW(numericAmount)} (approx. USD ${estimateUSD(numericAmount)})`
        : `주문 ${orderId} 확인 완료 · 결제금액 ₩${formatKRW(numericAmount)} (약 USD ${estimateUSD(numericAmount)})`;
    } else {
      orderInfo.textContent = isEnglish
        ? 'Your payment is confirmed. Detailed receipt will be sent by email.'
        : '결제가 확인되었습니다. 상세 영수증은 이메일로 안내됩니다.';
    }
  }

  // PDF 다운로드 링크 제공
  const downloadInfo = document.getElementById('download-info');
  if (downloadInfo) {
    let downloadHTML = '';

    if (productId === 'workbook_digital') {
      downloadHTML = `
        <div class="payment-download-card">
          <strong class="payment-download-title">${isEnglish ? 'Workbook Access' : '워크북 열람'}</strong><br><br>
          <a href="/product/workbook.html" target="_blank" class="payment-download-link">
            ${isEnglish ? 'Open Zero Point Workbook →' : '영점의 발견 열기 →'}
          </a>
          <br><br>
          <small class="payment-download-note">
            ${isEnglish
              ? 'Use <strong>Cmd/Ctrl + P</strong> in your browser and choose<br>"Save as PDF" to keep your personal copy.'
              : '브라우저에서 <strong>Cmd/Ctrl + P</strong>를 눌러<br>"PDF로 저장"을 선택하시면 디지털 보관본을 만들 수 있습니다.'}
          </small>
        </div>
      `;
    } else if (productId === 'workbook_riso') {
      downloadHTML = `
        <div class="payment-download-card">
          <strong class="payment-download-title">${isEnglish ? 'Order Received' : '주문 접수 완료'}</strong><br><br>
          <small class="payment-download-note">
            ${isEnglish
              ? 'Riso print orders are produced in limited batches (about 10-15 business days).<br>International shipping details are confirmed by email after payment.'
              : '리소 인쇄본은 결제 확인 후 순차 제작됩니다(통상 10-15영업일).<br>해외 배송 정보는 결제 후 이메일로 확정됩니다.'}
          </small>
        </div>
      `;
    } else if (productId === 'manual_pdf') {
      downloadHTML = `
        <div class="payment-download-card">
          <strong class="payment-download-title">다운로드</strong><br><br>
          <a href="../products/atelier-manual.html" target="_blank" class="payment-download-link">
            Atelier Manual 보기 →
          </a>
          <br><br>
          <small class="payment-download-note">
            브라우저에서 <strong>Cmd/Ctrl + P</strong>를 눌러<br>
            "PDF로 저장"을 선택하세요.
          </small>
        </div>
      `;
    } else if (productId === 'slow_object_001') {
      downloadHTML = `
        <div class="payment-download-card">
          <strong class="payment-download-title">다운로드</strong><br><br>
          <a href="../products/slow-object-001-scissors.html" target="_blank" class="payment-download-link">
            Slow Object Report #001 보기 →
          </a>
          <br><br>
          <small class="payment-download-note">
            브라우저에서 <strong>Cmd/Ctrl + P</strong>를 눌러<br>
            "PDF로 저장"을 선택하세요.
          </small>
        </div>
      `;
    }

    downloadInfo.innerHTML = downloadHTML;
  }
}

/**
 * 결제 실패 처리
 */
function handlePaymentFail() {
  const isEnglish = isEnglishSession();
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');
  const message = urlParams.get('message');
  const errorInfo = document.getElementById('error-info');

  console.error('결제 실패:', { code, message });

  const statusLead = document.getElementById('status-lead');
  if (statusLead) {
    statusLead.textContent = isEnglish ? 'Payment did not complete.' : '결제가 완료되지 않았습니다.';
  }

  const statusNote = document.getElementById('status-note');
  if (statusNote) {
    statusNote.textContent = isEnglish
      ? 'If the issue repeats, contact hello@woohwahae.kr and include your order time.'
      : '문제가 계속되면 결제 시각과 함께 hello@woohwahae.kr로 문의해주세요.';
  }

  const statusCta = document.getElementById('status-cta');
  if (statusCta) {
    statusCta.textContent = isEnglish ? 'Retry Purchase →' : '다시 시도하기 →';
  }

  if (errorInfo) {
    const fallback = isEnglish ? 'A payment processing error occurred.' : '결제 처리 중 문제가 발생했습니다.';
    const msg = message || fallback;
    errorInfo.textContent = code ? `[${code}] ${msg}` : msg;
    return;
  }
}
