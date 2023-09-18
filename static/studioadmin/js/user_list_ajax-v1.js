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

/**
   Executes a toggle click. Triggered by clicks on the regular student yes/no links.
 */
var processToggleRegularStudent = function()  {

   //In this scope, "this" is the button just clicked on.
   //The "this" in processResult is *not* the button just clicked
   //on.
   var button_just_clicked_on = $jq(this);

   //The value of the "data-user_id" attribute.
   var user_id = button_just_clicked_on.data('user_id');

   var processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', user_id='" + user_id + "'");
      $jq('#toggle_regular_student_' + user_id).html(result);
   }

   $jq.ajax(
       {
          url: '/studioadmin/users/' + user_id + '/toggle_regular_student/',
          dataType: 'html',
          success: processResult
          //Should also have a "fail" call as well.
       }
    );
};


/**
   Executes a toggle click. Triggered by clicks on the print disclaimer yes/no links.
 */
var processTogglePrintDisclaimer = function()  {
   var button_just_clicked_on = $jq(this);
   //The value of the "data-user_id" attribute.
   var user_id = button_just_clicked_on.data('user_id');

   var processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', user_id='" + user_id + "'");
      $jq('#toggle_print_disclaimer_' + user_id).html(result);
   }

   $jq.ajax(
       {
          url: '/studioadmin/users/' + user_id + '/toggle_print_disclaimer/',
          dataType: 'html',
          success: processResult
          //Should also have a "fail" call as well.
       }
    );
};


/**
   Executes a toggle click. Triggered by clicks on the subscribed yes/no links.
 */
var processToggleSubscribed = function()  {
   var button_just_clicked_on = $jq(this);
   //The value of the "data-user_id" attribute.
   var user_id = button_just_clicked_on.data('user_id');

   var processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', user_id='" + user_id + "'");
      $jq('#toggle_subscribed_' + user_id).html(result);
   }

   $jq.ajax(
       {
          url: '/studioadmin/users/' + user_id + '/toggle_subscribed/',
          dataType: 'html',
          success: processResult
          //Should also have a "fail" call as well.
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
$jq(function()  {
  /*
    There are many buttons having the class

      td_regular_student_button

    This attaches a listener to *every one*. Calling this again
    would attach a *second* listener to every button, meaning each
    click would be processed twice.
   */
  $jq('.td_regular_student_button').on("click", _.debounce(processToggleRegularStudent,
      MILLS_TO_IGNORE, true));
  $jq('.td_print_disclaimer_button').on("click", _.debounce(processTogglePrintDisclaimer,
      MILLS_TO_IGNORE, true));
    $jq('.td_subscribed_button').on("click", _.debounce(processToggleSubscribed,
      MILLS_TO_IGNORE, true));

  /*
    Warning: Placing the true parameter outside of the debounce call:

    $('#color_search_text').keyup(_.debounce(processSearch,
        MILLS_TO_IGNORE_SEARCH), true);

    results in "TypeError: e.handler.apply is not a function".
   */
});
