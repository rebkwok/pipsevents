
    const payment_button = document.querySelector('#payment-button');
    stripe_data = {
        stripe_account: payment_button.getAttribute("data-stripe_account"),
        customer_id: payment_button.getAttribute("data-customer_id"),
        stripe_api_key: payment_button.getAttribute("data-stripe_api_key"),
        return_url: payment_button.getAttribute("data-return_url"),
        price_id: payment_button.getAttribute("data-price_id"),
        amount: payment_button.getAttribute("data-amount"),
        backdate: payment_button.getAttribute("data-backdate")
    };

    stripe = Stripe(stripe_data.stripe_api_key, {stripeAccount: stripe_data.stripe_account});
    const appearance = {
        theme: 'stripe',
    };
    
    const options = {
        mode: 'subscription',
        amount: Number(stripe_data.amount),
        currency: 'gbp',
        appearance: appearance,
    };
        
    // Set up Stripe.js and Elements to use in checkout form
    const elements = stripe.elements(options);
        
    // Create and mount the Payment Element
    const paymentElementOptions = {
        layout: "accordion",
    };
    const paymentElement = elements.create("payment", paymentElementOptions);
    paymentElement.mount("#payment-element");
    console.log("Initialise")    
    console.log(elements)

    const form = document.getElementById('payment-form');
    const submitBtn = document.getElementById('payment-button');

    const handleError = (error) => {
        const messageContainer = document.querySelector('#error-message');
        messageContainer.textContent = error.message;
        submitBtn.disabled = false;
    }

    form.addEventListener('submit', async (event) => {
        // We don't want to let default form submission happen here,
        // which would refresh the page.
        event.preventDefault();
        setLoading(true);

        const {error: submitError} = await elements.submit();
        if (submitError) {
            handleError(submitError);
            return;
        }

        // Create the subscription
        console.log(stripe_data.backdate)
        const res = await fetch('/membership/subscription/create/', {
            method: "POST",
            body: JSON.stringify({
                customer_id: stripe_data.customer_id, 
                price_id: stripe_data.price_id, 
                backdate: stripe_data.backdate,
            }),
            headers: {
                'Content-Type': 'application/json',
                "X-CSRFToken": CSRF_TOKEN
            }
        });
        const {type, clientSecret} = await res.json();
        console.log("!!!")
        console.log(clientSecret)
        const confirmIntent = type === "setup" ? stripe.confirmSetup : stripe.confirmPayment;

        // Confirm the Intent using the details collected by the Payment Element
        const {error} = await confirmIntent({
            elements,
            clientSecret,
            confirmParams: {
            return_url: stripe_data.return_url,
            },
        });

        console.log(error)
        // This point will only be reached if there is an immediate error when
        // confirming the payment. Otherwise, your customer will be redirected to
        // your `return_url`. For some payment methods like iDEAL, your customer will
        // be redirected to an intermediate site first to authorize the payment, then
        // redirected to the `return_url`.
        if (error.type === "card_error" || error.type === "validation_error") {
            showError(error.message);
        } else {
            showError("An unexpected error occurred.");
        }
        setLoading(false);
    });

    // ------- UI helpers -------

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
            submitBtn.disabled = true;
            document.querySelector("#spinner").classList.remove("hidden");
            document.querySelector("#button-text").classList.add("hidden");
        } else {
            submitBtn.disabled = false;
            document.querySelector("#spinner").classList.add("hidden");
            document.querySelector("#button-text").classList.remove("hidden");
        }
    }

