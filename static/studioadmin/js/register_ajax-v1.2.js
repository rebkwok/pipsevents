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
const MILLS_TO_IGNORE = 500;

/**
   Executes a toggle click. Triggered by clicks on the regular student yes/no links.
 */

const processFailure = function(
   result, status, jqXHR)  {
  //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "'");
  if (result.responseText) {
    vNotify.error({text:result.responseText,title:'Error',position: 'bottomRight'});
  }
   };

const processToggleAttended = function()  {

   //In this scope, "this" is the button just clicked on.
   //The "this" in processResult is *not* the button just clicked
   //on.
   const button_just_clicked_on = $jq(this);

   //The value of the "data-booking_id" attribute.
   const booking_id = button_just_clicked_on.data('booking_id');
   const attendance = button_just_clicked_on.data('attendance');
   const unset = button_just_clicked_on.data('unset');

   const processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result.attended + "', status='" + status + "', jqXHR='" + jqXHR + "', booking_id='" + booking_id + "'");
      if(result.unset === true) {
           $jq('#booking-attended-' + booking_id).removeClass('btn-wm').addClass('btn-outline-secondary');
           $jq('#booking-noshow-' + booking_id).addClass('btn-outline-secondary');
           $jq('#booking-row-' + booking_id).removeClass('expired');
           $jq('#booking-status-' + booking_id).html(result.status_text);
      }  
       else if(result.attended === true) {
           $jq('#booking-attended-' + booking_id).addClass('btn-wm').removeClass('btn-outline-secondary');
           $jq('#booking-noshow-' + booking_id).addClass('btn-outline-secondary');
           $jq('#booking-row-' + booking_id).removeClass('expired');
           $jq('#booking-status-' + booking_id).html(result.status_text);
       } else {
           $jq('#booking-row-' + booking_id).addClass('expired');
           $jq('#booking-attended-' + booking_id).addClass('btn-outline-secondary').removeClass('btn-wm');
           $jq('#booking-noshow-' + booking_id).removeClass('btn-outline-secondary');
           $jq('#booking-status-' + booking_id).html(result.status_text);
       }

       if (result.alert_msg) {
        vNotify.error({text:result.alert_msg, title:'Error', position: 'bottomRight'});
      }

   };

   $jq.ajax(
       {
          url: '/studioadmin/register/' + booking_id + '/toggle_attended/' ,
          data: {'attendance': attendance},
          type: "POST",
          dataType: 'json',
          success: processResult,
          error: processFailure
       }
    );
};


const processUpdatePaid = function(
       result, status, jqXHR, booking_id)  {
      //console.log("sf result='" + result.paid + "', status='" + status + "', jqXHR='" + jqXHR + "', booking_id='" + booking_id + "'");

      if(result.paid === true) {
           $jq('#booking-paid-checkbox-' + booking_id).prop("checked", true);
          $jq('#booking-paid-checkbox-' + booking_id).attr("checked","checked");
           $jq('#booking-paid-' + booking_id).removeClass("register-unpaid");
           $jq('#booking-block-btn-content-' + booking_id).hide();
       } else {
           $jq('#booking-paid-checkbox-' + booking_id).prop("checked", false);
          $jq('#booking-paid-checkbox-' + booking_id).attr("checked", "");
          $jq('#booking-paid-' + booking_id).addClass("register-unpaid");
          if (result.has_available_block === true) {
            $jq('#booking-block-btn-content-' + booking_id).show();
          }
     }
       if (result.alert_msg) {
           if (result.alert_msg.status === 'error') {
               vNotify.error({text: result.alert_msg.msg, title: 'Error', position: 'bottomRight'});
           }
            else if (result.alert_msg.status === 'warning') {
                vNotify.warning({text: result.alert_msg.msg, title: '', position: 'bottomRight'});
           }
           else {
               vNotify.success({text: result.alert_msg.msg, title: '', position: 'bottomRight'});
           }
       }
    };


const processTogglePaid = function()  {

   //In this scope, "this" is the button just clicked on.
   //The "this" in processResult is *not* the button just clicked
   //on.
   const button_just_clicked_on = $jq(this);

   //The value of the "data-booking_id" attribute.
   const booking_id = button_just_clicked_on.data('booking_id');

   const processPaidDisplay =function(result, status, jqXHR) {
        processUpdatePaid(result, status, jqXHR, booking_id);
    };


   const processRegisterBlock = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', booking_id='" + booking_id + "'");
      $jq('#booking-block-' + booking_id).html(result);
    };

   const updateOnComplete  = function() {
        $jq.ajax(
            {
                url: '/studioadmin/register/' + booking_id + /assign_block/,
                dataType: 'html',
                type: 'GET',
                success: processRegisterBlock,
                error: processFailure
            }
        );
    };

   $jq.ajax(
       {
          url: '/studioadmin/register/' + booking_id + '/toggle_paid/' ,
          type: "POST",
          dataType: 'json',
          success: processPaidDisplay,
          complete: updateOnComplete,
          error: processFailure
       }
    );
};


const processAssignBlock = function()  {

   //In this scope, "this" is the button just clicked on.
   //The "this" in processResult is *not* the button just clicked
   //on.
   const button_just_clicked_on = $jq(this);

   //The value of the "data-booking_id" attribute.
   const booking_id = button_just_clicked_on.data('booking_id');

   const processResult = function(
       result, status, jqXHR)  {
      //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', booking_id='" + booking_id + "'");
       $jq('#booking-block-' + booking_id).html(result);
    };

   const processUpdatePaidDisplay = function(
       result, status, jqXHR) {
       //console.log("sf result='" + result + "', status='" + status + "', jqXHR='" + jqXHR + "', booking_id='" + booking_id + "'");
       //console.log("result.paid=" + result.paid);

       processUpdatePaid(result, status, jqXHR, booking_id)

   };

   const updateOnComplete  = function() {
        $jq.ajax(
            {
                url: '/studioadmin/register/' + booking_id + /toggle_paid/,
                dataType: 'json',
                type: "GET",
                success: processUpdatePaidDisplay,
                error: processFailure
            }
        );
    };

   $jq.ajax(
       {
          url: '/studioadmin/register/' + booking_id + '/assign_block/' ,
          type: "POST",
          dataType: 'html',
          success: processResult,
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
$jq(function()  {
  /*
    There are many buttons having the class

      td_regular_student_button

    This attaches a listener to *every one*. Calling this again
    would attach a *second* listener to every button, meaning each
    click would be processed twice.
   */
  $jq('.btn-attended').on("click", _.debounce(processToggleAttended, MILLS_TO_IGNORE, true));
  $jq('.btn-noshow').on("click", _.debounce(processToggleAttended, MILLS_TO_IGNORE, true));
  $jq('.booking-paid-checkbox').on("click", _.debounce(processTogglePaid, MILLS_TO_IGNORE, true));
  $jq('.booking-block-btn').on("click", _.debounce(processAssignBlock, MILLS_TO_IGNORE, true));
});
