
    $jq(function () {
        let elements;
        let stripe;
        let stripe_data;
        let checked_total;

        setupElements();
        checkTotal();
        initialize();
        checkStatus();

        document
        .querySelector("#payment-form")
        .addEventListener("submit", handleSubmit);

        let emailAddress = '';

        async function setupElements() {
            const payment_button = document.querySelector('#payment-button');
            stripe_data = {
                stripe_account: payment_button.getAttribute("data-stripe_account"),
                client_secret: payment_button.getAttribute("data-client_secret"),
                stripe_api_key: payment_button.getAttribute("data-stripe_api_key"),
                total: payment_button.getAttribute("data-total"),
                checkout_type: payment_button.getAttribute("data-checkout_type"),
                tbref: payment_button.getAttribute("data-tbref"),
                voucher_id: payment_button.getAttribute("data-voucher_id"),
                return_url: payment_button.getAttribute("data-return_url")
            };
        }


        // Fetches a payment intent and captures the client secret
        async function initialize() {
            const client_secret = stripe_data.client_secret
            stripe = Stripe(stripe_data.stripe_api_key, {stripeAccount: stripe_data.stripe_account});

            const appearance = {
                theme: 'stripe',
            };
            elements = stripe.elements(
                { appearance: appearance, clientSecret: client_secret}
            );

            const linkAuthenticationElement = elements.create("linkAuthentication");
            linkAuthenticationElement.mount("#link-authentication-element");

            linkAuthenticationElement.on('change', (event) => {
                emailAddress = event.value.email;
            });

            const paymentElementOptions = {
                layout: "accordion",
            };

            const paymentElement = elements.create("payment", paymentElementOptions);
            paymentElement.mount("#payment-element");
        }

        async function checkTotal() {
            const response = await fetch(
                '/check-total/?checkout_type=' + stripe_data.checkout_type 
                + "&tbref=" + stripe_data.tbref
                + "&voucher_id=" + stripe_data.voucher_id
            )
            checked_total = await response.json()
        };

        async function handleSubmit(e) {
            e.preventDefault();
            setLoading(true);
            
            if (checked_total.total !== stripe_data.total) {
                // Show error to your customer
                console.log("Actual total: " + checked_total.total)
                console.log("Cart total: " + stripe_data.total)
                showError("Your cart has changed, please return to the previous page and try again");
                setLoading(false);

            } else { 
            
                const { error } = await stripe.confirmPayment({
                    elements,
                    confirmParams: {
                    // Make sure to change this to your payment completion page
                    return_url: stripe_data.return_url,
                    receipt_email: emailAddress,
                    },
                });

                // This point will only be reached if there is an immediate error when
                // confirming the payment. Otherwise, your customer will be redirected to
                // your `return_url`. For some payment methods like iDEAL, your customer will
                // be redirected to an intermediate site first to authorize the payment, then
                // redirected to the `return_url`.
                if (error.type === "card_error" || error.type === "validation_error") {
                    showError(error.message);
                } else {
                    console.log(error);
                    showError("An unexpected error occurred.");
                }
                setLoading(false);
            }    
        }

    // Fetches the payment intent status after payment submission
    async function checkStatus() {
        const clientSecret = new URLSearchParams(window.location.search).get(
            "payment_intent_client_secret"
        );

        if (!clientSecret) {
            return;
        }

        const { paymentIntent } = await stripe.retrievePaymentIntent(clientSecret);

        switch (paymentIntent.status) {
            case "succeeded":
            showMessage("Payment succeeded!");
            break;
            case "processing":
            showMessage("Your payment is processing.");
            break;
            case "requires_payment_method":
            showError("Your payment was not successful, please try again.");
            break;
            default:
            showError("Something went wrong.");
            break;
        }
    }

    // ------- UI helpers -------

    function showMessage(messageText) {
        const messageContainer = document.querySelector("#payment-message");

        messageContainer.classList.remove("hidden");
        messageContainer.textContent = messageText;

        setTimeout(function () {
            messageContainer.classList.add("hidden");
            messageContainer.textContent = "";
        }, 5000);
        }
    
    function showError(messageText) {
        const messageContainer = document.querySelector("#payment-error");
        messageContainer.classList.remove("hidden");
        messageContainer.textContent = messageText;

        setTimeout(function () {
            messageContainer.classList.add("hidden");
            messageContainer.textContent = "";
        }, 5000);
        }

    // Show a spinner on payment submission
    function setLoading(isLoading) {
        if (isLoading) {
            // Disable the button and show a spinner
            document.querySelector("#payment-button").disabled = true;
            document.querySelector("#spinner").classList.remove("hidden");
            document.querySelector("#button-text").classList.add("hidden");
        } else {
            document.querySelector("#payment-button").disabled = false;
            document.querySelector("#spinner").classList.add("hidden");
            document.querySelector("#button-text").classList.remove("hidden");
        }
    }
});
