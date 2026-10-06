/** Razorpay Checkout, loaded only on the page that sells credits.
 *
 *  The script is Razorpay's hosted checkout.js; the card, UPI and netbanking forms all
 *  live inside its own frame, so no payment details ever touch this app. What comes back
 *  to us is an order id, a payment id and a signature, which the backend verifies before
 *  it grants anything.
 */

import type { CreditOrder, PaymentConfirmation } from "./types";

const CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

interface RazorpayInstance {
  open: () => void;
  on: (event: string, cb: (response: { error?: { description?: string } }) => void) => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance;
  }
}

let loading: Promise<void> | null = null;

export function loadCheckout(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.Razorpay) return Promise.resolve();
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = CHECKOUT_SRC;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        loading = null; // let the next click try again
        script.remove();
        reject(new Error("The payment window could not be loaded."));
      };
      document.body.appendChild(script);
    });
  }
  return loading;
}

export type CheckoutResult =
  | { status: "paid"; confirmation: PaymentConfirmation }
  | { status: "dismissed" }
  | { status: "failed"; message: string };

/** Open Checkout for an order and resolve once the customer pays or gives up.
 *
 *  A failed attempt does not close the Razorpay window; the customer can retry with
 *  another method there. So "failed" is only reported if they then close it.
 */
export async function openCheckout(order: CreditOrder): Promise<CheckoutResult> {
  await loadCheckout();
  const Razorpay = window.Razorpay;
  if (!Razorpay) throw new Error("The payment window could not be loaded.");

  return new Promise<CheckoutResult>((resolve) => {
    let lastError: string | null = null;
    const rzp = new Razorpay({
      key: order.key_id,
      order_id: order.order_id,
      amount: order.amount,
      currency: order.currency,
      name: order.name,
      description: `${order.pack.credits} credits (${order.pack.name})${order.test_mode ? " · test mode, no real money" : ""}`,
      prefill: order.prefill,
      theme: { color: "#13201a" }, // --brand
      handler: (response: PaymentConfirmation) =>
        resolve({ status: "paid", confirmation: response }),
      modal: {
        ondismiss: () =>
          resolve(lastError ? { status: "failed", message: lastError } : { status: "dismissed" }),
      },
    });
    rzp.on("payment.failed", (response) => {
      lastError = response.error?.description || "The payment did not go through.";
    });
    rzp.open();
  });
}
