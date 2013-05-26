
$(document).ready(function() {

    // Next two vars are deliberately in global scope
    utc_clock_div = $("#utc_clock");
    server_time_offset = 0;
    
    init_server_clock_offset();
    set_utc_clock();

    function init_server_clock_offset() {
        var sent = new Date().getTime();
        $.getJSON("/get_server_time/", {}, function(data) {set_utc_offset(data, sent)});
    }

    function set_utc_offset(data, sent) {
        var now = new Date().getTime();
        var middle_time = new Date(sent + (now-sent)/2); // account for time to make and receive request
        server_time_offset = data["server_time"] - middle_time;
    }

    function set_utc_clock() {
        var now = new Date(new Date().getTime() + server_time_offset);
        var clock_text = now.pprint();
        utc_clock_div.text(clock_text);
        next_full_second = 1000 - now.getMilliseconds();
        setTimeout(set_utc_clock, next_full_second);
    }

    $("#more_toggler").click(function(e) {
        var el = $("#more_languages");
        var toggler = $(e.target);
        if (el.css("display") == "none") {
            el.css("display", "block");
            toggler.text(gettext("Less"));
        }
        else {
            el.css("display", "none");
            toggler.text(gettext("More"));
        }
    });
});