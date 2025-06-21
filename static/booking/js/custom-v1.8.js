//http://xdsoft.net/jqplugins/datetimepicker/
Date.parseDate = function( input, format ){
  return moment(input,format).toDate();
};
Date.prototype.dateFormat = function( format ){
  return moment(this).format(format);
};

var timeoutID;

var $jq = jQuery.noConflict();

function timeoutShoppingBasket() {
  var bookingsPaypalForm = document.getElementById("checkout-bookings-total-and-paypalform");
  var blocksPaypalForm = document.getElementById("checkout-blocks-total-and-paypalform");
  var giftPaypalForm = document.getElementById("gift-voucher-paypal-form");
  if (bookingsPaypalForm !== null) {
      bookingsPaypalForm.innerHTML = '<div class="btn btn-warning reload-btn" onclick=location.reload();><span class="fas fa-sync-alt"></span> Refresh basket</div>';
  }
  if (blocksPaypalForm !== null) {
      blocksPaypalForm.innerHTML = '<div class="btn btn-warning reload-btn" onclick=location.reload();><span class="fas fa-sync-alt"></span> Refresh basket</div>';
  }
    if (giftPaypalForm !== null) {
      giftPaypalForm.innerHTML = '<div class="btn btn-warning reload-btn" onclick=location.reload();><span class="fas fa-sync-alt"></span> Refresh</div>';
  }

}


$jq(function () {

    timeoutID = window.setTimeout(timeoutShoppingBasket, 60*1000);

    $jq(function() {
        // messages timeout for 5 sec
        setTimeout(function() {
            $jq('#message-row').fadeOut('slow');
        }, 5000); // <-- time in milliseconds, 1000 =  1 sec
    });

    // blocks modal in menu bar
    $jq(".blockmodalbtn").on("click", function(ev) { // for each edit url
        ev.preventDefault(); // prevent navigation
        var url = $jq(this).data("url"); // get the form url
        $jq("#BlocksModal").load(url, function() { // load the url into the modal
            $jq(this).modal('show'); // display the modal on url load
        });
        return false; // prevent the click propagation
    });

    $jq(function () {
        $jq('[data-toggle="tooltip"]').tooltip()
      })

    $jq('form.dirty-check').areYouSure();

    $jq('#datetimepicker').datetimepicker({
        format:'D MMM YYYY HH:mm',
        sideBySide: true
    });
    $jq('#start_datetimepicker').datetimepicker({
        format:'D MMM YYYY HH:mm',
        sideBySide: true
    });
    $jq('#end_datetimepicker').datetimepicker({
        format:'D MMM YYYY HH:mm',
        sideBySide: true
    });

    $jq('#datepicker').datetimepicker({
        format:'D MMM YYYY',
    });

    $jq('.blockdatepicker').datetimepicker({
        format:'D MMM YYYY',
        widgetPositioning: {
            horizontal: 'left',
            vertical: 'bottom'
        }
    });

    $jq('#datepicker1').datetimepicker({
        format:'D MMM YYYY',
    });

    $jq('#logdatepicker').datetimepicker({
        format:'D-MMM-YYYY',
    });

    for(var i = 0; i < 5; i++) {
        $jq('#datepicker_startdate_' + i).datetimepicker({
            format:'ddd D MMM YYYY',
            useCurrent: true
        });

        $jq('#datepicker_enddate_' + i).datetimepicker({
            format:'ddd D MMM YYYY',
        });
    }

    $jq('#datepicker_registerdate').datetimepicker({
        format:'ddd D MMM YYYY',
        useCurrent: true
    });

    $jq('#timepicker').datetimepicker({
        format:'HH:mm',
    });

    $jq('#dobdatepicker').datetimepicker({
        format:'D MMM YYYY',
        defaultDate: '1990/01/01',
    });

    $jq('#eventdatepicker').datetimepicker({
        format:'D MMM YYYY',
    });


    $jq('.collapse')
        .on('shown.bs.collapse', function() {
            if(this.id) {
                $jq(this)
                    .parent()
                    .find("." + this.id + ".fa-plus-square")
                    .removeClass("fa-plus-square")
                    .addClass("fa-minus-square");
            }
        })
        .on('hidden.bs.collapse', function() {
            if(this.id) {
                $jq(this)
                    .parent()
                    .find("." + this.id + ".fa-minus-square")
                    .removeClass("fa-minus-square")
                    .addClass("fa-plus-square");
            }
        });

});


//Add CSRF tokens for ajax forms
$jq(function() {

    // This function gets cookie with a given name
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = $jq.trim(cookies[i]);
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) == (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    var csrftoken = getCookie('csrftoken');

    /*
    The functions below will create a header with csrftoken
    */

    function csrfSafeMethod(method) {
        // these HTTP methods do not require CSRF protection
        return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
    }
    function sameOrigin(url) {
        // test that a given url is a same-origin URL
        // url could be relative or scheme relative or absolute
        var host = document.location.host; // host + port
        var protocol = document.location.protocol;
        var sr_origin = '//' + host;
        var origin = protocol + sr_origin;
        // Allow absolute or scheme relative URLs to same origin
        return (url == origin || url.slice(0, origin.length + 1) == origin + '/') ||
            (url == sr_origin || url.slice(0, sr_origin.length + 1) == sr_origin + '/') ||
            // or any other URL that isn't scheme relative or absolute i.e relative.
            !(/^(\/\/|http:|https:).*/.test(url));
    }

    $jq.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && sameOrigin(settings.url)) {
                // Send the token to same-origin, relative URLs only.
                // Send the token only if the method warrants CSRF protection
                // Using the CSRFToken value acquired earlier
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });

});
