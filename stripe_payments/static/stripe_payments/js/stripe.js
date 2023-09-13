var MILLS_TO_IGNORE = 1000;

var $jq = jQuery.noConflict();

$jq(document).ready(function()  {
    // Set up Stripe.js and Elements to use in checkout form
    var setupElements = function() {
      var card_button = document.getElementById('card-button');
      var stripe_account = card_button.getAttribute("data-stripe_account")
      var client_secret = card_button.getAttribute("data-client_secret")
      var stripe_api_key = card_button.getAttribute("data-stripe_api_key")
      var total = card_button.getAttribute("data-total")
      var checkout_type = card_button.getAttribute("data-checkout_type")
      var tbref = card_button.getAttribute("data-tbref")
      var voucher_id = card_button.getAttribute("data-voucher_id")

      var stripe = Stripe(stripe_api_key, {stripeAccount: stripe_account});
      var elements = stripe.elements();
      var style = {
        base: {
          color: "#32325d",
          fontFamily: '"Helvetica Neue", Helvetica, sans-serif',
          fontSmoothing: "antialiased",
          fontSize: "16px",
          "::placeholder": {
            color: "#aab7c4"
          }
        },
        invalid: {
          color: "#fa755a",
          iconColor: "#fa755a"
        }
      };

      var payment = elements.create("payment", { style: style });
      payment.mount("#payment-element");

      payment.on('change', ({error}) => {
      const displayError = document.getElementById('payment-errors');
      if (error) {
        displayError.textContent = error.message;
      } else {
        displayError.textContent = '';
      }
    });

      return {
        elements: elements,
        stripe: stripe,
        payment: payment,
        client_secret: client_secret,
        total: total,
        checkout_type: checkout_type,
        tbref: tbref,
        voucher_id: voucher_id,
      };
    };

    // Disable the button until we have Stripe set up on the page

    var stripe_data = setupElements()

    // Handle form submission.
    var form = document.getElementById("payment-form");

    form.addEventListener("submit", function(event) {
      event.preventDefault();

      var response = fetch(
        '/check-total/?checkout_type=' + stripe_data.checkout_type 
        + "&tbref=" + stripe_data.tbref
        + "&voucher_id=" + stripe_data.voucher_id
        ).then(function(response) {
          return response.json();
        }).then(function(check_total) {
            console.log(check_total);
            console.log(stripe_data.total);
            var current_total = check_total.total

            if (current_total !== stripe_data.total) {
            // Show error to your customer
            showError("Your cart has changed, please return to the shopping cart page and try again");
          } else {
            // Total is up to date, make payment
            pay(stripe_data);
          }
        });

    });

    var pay = function(stripe_data) {
      // console.log(stripe_data.stripe);
      // console.log(stripe_data.card);
      // console.log(stripe_data.client_secret);
      changeLoadingState(true);

      stripe = stripe_data.stripe
      payment = stripe_data.payment
      client_secret = stripe_data.client_secret
      var cardholder_name = document.getElementById('cardholder-name').value
      var cardholder_email = document.getElementById('cardholder-email').value
      // Initiate the payment.
      // If authentication is required, confirmCardPayment will automatically display a modal
      stripe_data.elements.submit()
        .then(function(result) {
          if (result.error) {
            // Show error to your customer
            showError(result.error.message);
          } else {
            // The payment has been processed!
            orderComplete(result);
          }
        });
    };

    /* ------- Post-payment helpers ------- */

    /* Shows a success / error message when the payment is complete */
    var orderComplete = function(result) {
      // Just for the purpose of the sample, show the PaymentIntent response object

        var paymentIntent = result.paymentIntent;
        // var paymentIntentJson = JSON.stringify(paymentIntent, null, 2);

        // post data and show new page
        var form2 =document.getElementById("payload");
        var input = document.getElementById("data-payload")
        input.value = JSON.stringify({"id": paymentIntent.id});
        form2.submit();
        changeLoadingState(false);

    };

    var showError = function(errorMsgText) {
      changeLoadingState(false);
      var errorMsg = document.querySelector(".sr-field-error");
      errorMsg.textContent = errorMsgText;
      setTimeout(function() {
        errorMsg.textContent = "";
      }, 4000);
    };

    // Show a spinner on payment submission
    var changeLoadingState = function(isLoading) {
      if (isLoading) {
        document.getElementById("card-button").disabled = true;
        document.querySelector("#spinner").classList.remove("hidden");
        document.querySelector("#button-text").classList.add("hidden");
      } else {
        document.getElementById("card-button").disabled = false;
        document.querySelector("#spinner").classList.add("hidden");
        document.querySelector("#button-text").classList.remove("hidden");
      }
    };

});
