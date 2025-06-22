


var $jq = jQuery.noConflict();

//http://xdsoft.net/jqplugins/datetimepicker/
Date.parseDate = function( input, format ){
    return moment(input,format).toDate();
  };
  Date.prototype.dateFormat = function( format ){
    return moment(this).format(format);
  };


$jq(function() {
    //http://tablesorter.com/docs/
    $jq("#sortTable").tablesorter();

    $jq('#select-all').click(function (event) {  //on click
        if (this.checked) { // check select status
            $jq('.select-checkbox').each(function () { //loop through each checkbox
                this.checked = true;  //select all checkboxes with class "select-checkbox"
            });
        } else {
            $jq('.select-checkbox').each(function () { //loop through each checkbox
                this.checked = false; //deselect all checkboxes with class "select-checkbox"
            });
        }
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
    
})

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
