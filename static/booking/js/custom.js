// Custom JavaScript for the toggle checkboxes and select dropdowns
//jQuery('.toggle-checkbox').bootstrapSwitch();
//$('.custom-select').selectpicker();

//http://xdsoft.net/jqplugins/datetimepicker/
Date.parseDate = function( input, format ){
  return moment(input,format).toDate();
};
Date.prototype.dateFormat = function( format ){
  return moment(this).format(format);
};

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

//http://digitalbush.com/projects/masked-input-plugin/
jQuery(function($) {
    $('#timemask').mask("99:99", {placeholder:"HH:MM"});
    })


//For the register dropdown
//function FilterBlocks(index) {
//    var mainform = document.getElementById('booking_main_form');
//    mainform.submit();

//    var selected_user = document.getElementById("id_user"+index);
//    var user_id = selected_user.value;

//    new Ajax.Request('/ajax_block_feed/', {
//        method: 'post',
//        parameters: $H({'user_id':user_id}),
//        onSuccess: function(blocklist) {
//            debugger;
//            var e = document.getElementById("id_block"+index)
//            if(blocklist.responseText)
//                e.update(blocklist.responseText)
//        }
//    }); // end new Ajax.Request
//}
