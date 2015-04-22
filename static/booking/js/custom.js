// Custom JavaScript for the toggle checkboxes and select dropdowns
$('.toggle-checkbox').bootstrapSwitch();
$('.custom-select').selectpicker();

//For the register dropdown
function FilterBlocks(index) {
    var mainform = document.getElementById('booking_main_form');
    mainform.submit();

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
}
