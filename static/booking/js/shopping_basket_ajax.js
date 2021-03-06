/*
  This file must be imported immediately-before the close-</body> tag,
  and after JQuery and Underscore.js are imported.
*/
/**
  The number of milliseconds to ignore clicks on the *same* like
  button, after a button *that was not ignored* was clicked. Used by
  `$(document).ready()`.
  Equal to <code>500</code>.
 */
var MILLS_TO_IGNORE = 500;


var processBookingRemoveRequest = function()  {

    //In this scope, "this" is the button just clicked on.
    //The "this" in processResult is *not* the button just clicked
    //on.
    var $button_just_clicked_on = $(this);

    var booking_id = $button_just_clicked_on.data('booking_id');
    var booking_code = $button_just_clicked_on.data('booking_code');

    var processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', user_id='" + user_id + "'");
      $('#bookingrow-' + booking_id).html('');
   }

    var updateOnComplete  = function() {
        $.ajax(
            {
                url: '/bookings/ajax-update-shopping-basket/',
                dataType: 'html',
                success: processShoppingBasketCount
                //Should also have a "fail" call as well.
            }
        );

        $.ajax(
            {
                url: '/bookings/shopping-basket-total/bookings/' + '?code=' + booking_code,
                dataType: 'html',
                success: updateBookingsTotalAndPaypal
                //Should also have a "fail" call as well.
            }
        );
    };

    var processShoppingBasketCount = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "'");
      $('#shopping-basket-menu').html(result);
      $('#shopping-basket-menu-xs').html(result);
   }

    var updateBookingsTotalAndPaypal = function (result, status, jqXHR)  {
        $('#checkout-bookings-total-and-paypalform').html(result)
    };

    var processFailure = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "'");
      if (result.responseText) {
        vNotify.error({text:"Something went wrong", title:'Error',position: 'bottomRight'});
      }
   }

   $.ajax(
       {
          url: '/booking/cancel/' + booking_id + '/?ref=basket',
          dataType: 'html',
          type: 'POST',
          success: processResult,
          //Should also have a "fail" call as well.
          complete: updateOnComplete,
          error: processFailure
       }
    );

};


var processBlockRemoveRequest = function()  {

    //In this scope, "this" is the button just clicked on.
    //The "this" in processResult is *not* the button just clicked
    //on.
    var $button_just_clicked_on = $(this);

    var block_id = $button_just_clicked_on.data('block_id');
    var block_code = $button_just_clicked_on.data('block_code');

    var processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', user_id='" + user_id + "'");
      $('#blockrow-' + block_id).html('');
   }

    var updateOnComplete  = function() {
        $.ajax(
            {
                url: '/bookings/ajax-update-shopping-basket/',
                dataType: 'html',
                success: processShoppingBasketCount
                //Should also have a "fail" call as well.
            }
        );

        $.ajax(
            {
                url: '/bookings/shopping-basket-total/blocks/' + '?code=' + block_code,
                dataType: 'html',
                success: updateBlocksTotalAndPaypal
                //Should also have a "fail" call as well.
            }
        );
    };

    var processShoppingBasketCount = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "'");
      $('#shopping-basket-menu').html(result);
      $('#shopping-basket-menu-xs').html(result);
   }

    var updateBlocksTotalAndPaypal = function (result, status, jqXHR)  {
        $('#checkout-blocks-total-and-paypalform').html(result)
    };

    var processFailure = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "'");
      if (result.responseText) {
        vNotify.error({text:result.responseText,title:'Error',position: 'bottomRight'});
      }
   }

   $.ajax(
       {
          url: '/blocks/' + block_id + '/delete/?ref=basket',
          dataType: 'html',
          type: 'POST',
          success: processResult,
          //Should also have a "fail" call as well.
          complete: updateOnComplete,
          error: processFailure
       }
    );

};



/**
   The Ajax "main" function. Attaches the listeners to the elements on
   page load, each of which only take effect every
   <link to MILLS_TO_IGNORE> seconds.

   This protection is only against a single user pressing buttons as fast
   as they can. This is in no way a protection against a real DDOS attack,
   of which almost 100% bypass the client (browser) (they instead
   directly attack the server). Hence client-side protection is pointless.

   - http://stackoverflow.com/questions/28309850/how-much-prevention-of-rapid-fire-form-submissions-should-be-on-the-client-side

   The protection is implemented via Underscore.js' debounce function:
  - http://underscorejs.org/#debounce

   Using this only requires importing underscore-min.js. underscore-min.map
   is not needed.
 */
$(document).ready(function()  {
  /*
    There are many buttons having the class

      td_ajax_book_button

    This attaches a listener to *every one*. Calling this again
    would attach a *second* listener to every button, meaning each
    click would be processed twice.
   */
  $('.booking_remove_btn').click(_.debounce(processBookingRemoveRequest,
      MILLS_TO_IGNORE, true));
  $('.block_remove_btn').click(_.debounce(processBlockRemoveRequest,
      MILLS_TO_IGNORE, true));

  /*
    Warning: Placing the true parameter outside of the debounce call:

    $('#color_search_text').keyup(_.debounce(processSearch,
        MILLS_TO_IGNORE_SEARCH), true);

    results in "TypeError: e.handler.apply is not a function".
   */
});