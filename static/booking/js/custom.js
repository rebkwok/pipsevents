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

jQuery('#logdatepicker').datetimepicker({
    format:'DD-MMM-YYYY',
    formatTime:'HH:mm',
    timepicker: false,
    closeOnDateSelect: true,
    scrollMonth: false,
    scrollTime: false,
    scrollInput: false,
});

jQuery('#datepicker_startdate').datetimepicker({
    format:'ddd DD MMM YYYY',
    formatTime:'HH:mm',
    timepicker: false,
    minDate: 0,
    closeOnDateSelect: true,
    scrollMonth: false,
    scrollTime: false,
    scrollInput: false,
});

jQuery('#datepicker_enddate').datetimepicker({
    format:'ddd DD MMM YYYY',
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

//http://tablesorter.com/docs/
$(document).ready(function()
    {
        $("#sortTable").tablesorter();
    }
);

$(document).ready(function() {
    $('#select-all').click(function(event) {  //on click
        if(this.checked) { // check select status
            $('.select-checkbox').each(function() { //loop through each checkbox
                this.checked = true;  //select all checkboxes with class "select-checkbox"
            });
        }else{
            $('.select-checkbox').each(function() { //loop through each checkbox
                this.checked = false; //deselect all checkboxes with class "select-checkbox"                       
            });
        }
    });

});
