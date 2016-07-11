function startTime() {
    var today = new Date();
    var h = today.getHours();
    var m = today.getMinutes();
    var s = today.getSeconds();
    var utc_h = today.getUTCHours();
    var utc_m = today.getUTCMinutes();
    var utc_s = today.getUTCSeconds();

    m = checkTime(m);
    s = checkTime(s);
    utc_m = checkTime(utc_m);
    utc_s = checkTime(utc_s);
    document.getElementById('show-clock').innerHTML =
        '<br/><div class="container"><div class="row"><div class="col-xs-8 col-sm-3 col-sm-offset-8 col-md-2 col-md-offset-9" style="padding-left: 5%; padding-right: 0;">Local Time: </div><div class="col-xs-1">' +
        h + ':' + m + ':' + s +
        '</div></div><div class="row"><div class="col-xs-8 col-sm-3 col-sm-offset-8 col-md-2 col-md-offset-9" style="padding-left: 5%; padding-right: 0;">Server Time (UTC):</div><div class="col-xs-1">' +
        + utc_h + ':' + utc_m + ':' + utc_s +
        '</div></div></div>';
    var t = setTimeout(startTime, 500);
}
function checkTime(i) {
    if (i < 10) {i = "0" + i};  // add zero in front of numbers < 10
    return i;
}
