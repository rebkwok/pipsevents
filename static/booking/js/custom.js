//http://xdsoft.net/jqplugins/datetimepicker/
Date.parseDate = function( input, format ){
  return moment(input,format).toDate();
};
Date.prototype.dateFormat = function( format ){
  return moment(this).format(format);
};


jQuery(document).ready(function () {

    jQuery('form.dirty-check').areYouSure();

    jQuery('#datetimepicker').datetimepicker({
        format:'DD MMM YYYY HH:mm',
        formatTime:'HH:mm',
        formatDate:'DD MM YYYY',
        minDate: 0,
        step: 5,
        defaultTime: '19:00',
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,

    });

    jQuery('#datepicker').datetimepicker({
        format:'DD MMM YYYY',
        formatTime:'HH:mm',
        timepicker: false,
        minDate: 0,
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    jQuery('.blockdatepicker').datetimepicker({
        format:'DD MMM YYYY',
        startDate: new Date(),
        timepicker: false,
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    jQuery('#datepicker1').datetimepicker({
        format:'DD MMM YYYY',
        formatTime:'HH:mm',
        timepicker: false,
        minDate: 0,
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    jQuery('#logdatepicker').datetimepicker({
        format:'DD-MMM-YYYY',
        formatTime:'HH:mm',
        timepicker: false,
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    for(var i = 0; i < 5; i++) {
        jQuery('#datepicker_startdate_' + i).datetimepicker({
            format:'ddd DD MMM YYYY',
            formatTime:'HH:mm',
            timepicker: false,
            minDate: 0,
            closeOnDateSelect: true,
            scrollMonth: false,
            scrollTime: false,
            scrollInput: false
        });

        jQuery('#datepicker_enddate_' + i).datetimepicker({
            format:'ddd DD MMM YYYY',
            formatTime:'HH:mm',
            timepicker: false,
            minDate: 0,
            closeOnDateSelect: true,
            scrollMonth: false,
            scrollTime: false,
            scrollInput: false
        });
    }

    jQuery('#datepicker_registerdate').datetimepicker({
        format:'ddd DD MMM YYYY',
        formatTime:'HH:mm',
        timepicker: false,
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    jQuery('#timepicker').datetimepicker({
        format:'HH:mm',
        formatTime:'HH:mm',
        step: 5,
        defaultTime: '19:00',
        datepicker: false,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    jQuery('#dobdatepicker').datetimepicker({
        format:'DD MMM YYYY',
        formatTime:'HH:mm',
        timepicker: false,
        defaultDate: '1990/01/01',
        closeOnDateSelect: true,
        scrollMonth: false,
        scrollTime: false,
        scrollInput: false,
    });

    //http://digitalbush.com/projects/masked-input-plugin/
    jQuery('#timemask').mask("99:99", {placeholder: "HH:MM"});


    //http://tablesorter.com/docs/
    jQuery("#sortTable").tablesorter();

    jQuery('#select-all').click(function (event) {  //on click
        if (this.checked) { // check select status
            jQuery('.select-checkbox').each(function () { //loop through each checkbox
                this.checked = true;  //select all checkboxes with class "select-checkbox"
            });
        } else {
            jQuery('.select-checkbox').each(function () { //loop through each checkbox
                this.checked = false; //deselect all checkboxes with class "select-checkbox"
            });
        }
    });

    jQuery('.collapse')
        .on('shown.bs.collapse', function() {
            jQuery(this)
                .parent()
                .find("." + this.id + ".fa-plus-square")
                .removeClass("fa-plus-square")
                .addClass("fa-minus-square");
        })
        .on('hidden.bs.collapse', function() {
            jQuery(this)
                .parent()
                .find("." + this.id + ".fa-minus-square")
                .removeClass("fa-minus-square")
                .addClass("fa-plus-square");
        });

});


//Add CSRF tokens for ajax forms
$(function() {

    // This function gets cookie with a given name
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = jQuery.trim(cookies[i]);
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

    $.ajaxSetup({
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