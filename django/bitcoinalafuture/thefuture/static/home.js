
$(document).ready(function() {

    var addresses = {};
    var has_local_storage = true;
   
    $(document).ajaxError(function(event,request,settings){
        $("#deposit_address").text("");
        return false;
    });

    $(document).ajaxSuccess(function(event,request,settings) {
        $("#error").text("");
    });
    
    var earlier_time = new Date().getTime();
    var later_time = new Date().getTime();

    init_text_margins();
    init_datetimepicker();
    init_form_fields();
    init_ajax_form();
    init_local_storage();
    init_fast_populate_links();
    init_thefuture_pagination();
    populate_values_from_fragment();
    get_the_future();
    $("#price").focus();

    //TODO consider using local storage to track 'your deposits'

    function init_text_margins() {
        var calculated_width = ($(window).innerWidth() - $("#prediction").outerWidth(true)) / 2;
        $("#explanation_container").css("margin-left", calculated_width);
        $("#explanation_container").css("margin-right", calculated_width);
        $("#explanation_container").css("visibility", "visible");
    }
    
    function init_datetimepicker() {
        var now = new Date();
        $("#datetimepicker").datetimepicker({
            dateFormat: "yy-mm-dd",
            showButtonPanel: false,
            year: now.getUTCFullYear(),
            month: now.getUTCMonth(),
            date: now.getUTCDate(),
            hour: now.getUTCHours(),
            minute: now.getUTCMinutes(),
            timeText: gettext("Time"),
            hourText: gettext("Hour"),
            minuteText: gettext("Minute"),
            secondText: gettext("Second"),
            currentText: gettext("Now"),
            closeText: gettext("Close"),
        });
    }

    function init_local_storage() {
        has_local_storage = typeof(Storage)!=="undefined";
        if(has_local_storage) {
            if (typeof(localStorage.addresses) != "undefined") {
                addresses = JSON.parse(localStorage.addresses);
            }
            else {
                localStorage.addresses = JSON.stringify({});
            }
        }
    }

    function init_form_fields() {
        $("#lt_gt_select").focus(reset_deposit_address);
        $("#price").focus(reset_deposit_address);
        $("#datetimepicker").focus(reset_deposit_address);
        $("#winning_address").focus(reset_deposit_address);
    }

    function init_ajax_form() {
        $("#submit_prediction_button").click(function() {
            $("#submit_prediction_button").attr("disabled", "disabled");
            $("#wait_for_address").css("display", "inline-block");
            var return_address = $("#winning_address").val();
            var time_to_check_js = new Date($("#datetimepicker").val() + ":00+0000").getTime();
            var params = {
                "lt": $("#lt_gt_select").val(),
                "price": $("#price").val(),
                "time_to_check": time_to_check_js,
                "return_address": return_address
            }
            $.post("/make_new_prediction/", params, handle_new_address)
            .error(function() {
                $("#wait_for_address").css("display", "none");
                $("#submit_prediction_button").attr("disabled", "");
            });
            locally_store_address(return_address, "mine")
        });
    }

    function init_fast_populate_links() {
        $(".fast_populate_link").each(function(i,e) {
            $(e).click(populate_values_from_fragment);
        });
    }

    function init_thefuture_pagination() {
        $("#earlier").click(function() {
            get_the_past();
        });
        $("#later").click(function() {
            get_the_future();
        });
    }

    function handle_new_address(data) {
        $("#wait_for_address").css("display", "none")
        $("#submit_prediction_button").attr("disabled", "");
        reset_deposit_address();
        var receive_address = data["address"];
        $("#deposit_address").text(receive_address); // TODO make this also a qr and a bitcoin url
    }

    function locally_store_address(address, wallet_owner) {
        addresses[address] = wallet_owner;
        localStorage.addresses = JSON.stringify(addresses);
    }
    
    function get_the_future() {
        $.getJSON("/the_future/", {"after": later_time}, display_the_future);
    }

    function get_the_past() {
        $.getJSON("/the_future/", {"before": earlier_time}, display_the_future);
    }

    function display_the_future(data) {

        if (data.length > 0) {
            earlier_time = new Date(data[0]["expires"]).getTime();
            later_time = new Date(data[data.length-1]["expires"]).getTime();
        
            $("#the_future_table").remove();
            var predictions = data["predictions"];
            var table = $(document.createElement("table"));
            table.attr("id", "the_future_table");
            table.addClass("home_table");

            var heading_row = create_future_table_heading();
            table.append(heading_row);

            for (var data_index=0; data_index<data.length; data_index++) {
                var prediction_group = data[data_index];
                var row = create_future_row(prediction_group);
                table.append(row);
            }
            $("#the_future").append(table);
        }
    }

    function create_future_table_heading() {
        var heading = $(document.createElement("thead"));
        var row = $(document.createElement("tr"));
        heading.append(row);

        var date_heading = $(document.createElement("th"));
        date_heading.text(gettext("Concludes at"));
        row.append(date_heading);

        var target_heading = $(document.createElement("th"));
        target_heading.text(gettext("Price"));
        row.append(target_heading);

        var above_heading = $(document.createElement("th"));
        above_heading.text(gettext("More than"));
        row.append(above_heading);

        var below_heading = $(document.createElement("th"));
        below_heading.text(gettext("Less than"));
        row.append(below_heading);

        return heading;
    }
    
    function create_future_row(prediction_group) {
        var expires = prediction_group["expires"];
        var predictions = prediction_group["predictions"];

        var row = $(document.createElement("tr"));

        var expiry_date = new Date(expires);
        var expire_cell = $(document.createElement("td"));
        expire_cell.text(expiry_date.to_datetimepicker_format())
        row.append(expire_cell);

        var price_cell = $(document.createElement("td"));
        row.append(price_cell);

        var above_cell = $(document.createElement("td"));
        row.append(above_cell);

        var below_cell = $(document.createElement("td"));
        row.append(below_cell);

        for (var prediction_index=0; prediction_index<predictions.length; prediction_index++) {

            var prediction = predictions[prediction_index];

            var div_class = "future_table_div";
            if (prediction_index == 0) {
                div_class = "future_table_div_first";
            }
            if (prediction_index == predictions.length - 1) {
                div_class = "future_table_div_last";
            }
            if (prediction_index == 0 &&
                prediction_index == predictions.length - 1) {
                div_class = "";
            }

            var price = prediction["target_price"];
            var price_div = $(document.createElement("div"));
            price_div.addClass(div_class);
            var price_link = $(document.createElement("a"));
            price_link.text("$" + price);
            price_link.attr("href", "/prediction/" + prediction["id"] + "/");
            price_div.append(price_link);
            price_cell.append(price_div);
            
            var deposits = prediction["deposits"]
            var amount_above = 0;
            var count_above = 0;
            var amount_below = 0;
            var count_below = 0;
            for (var deposit_index=0; deposit_index<deposits.length; deposit_index++) {
                var deposit = deposits[deposit_index];
                if(deposit["lt"]) {
                    amount_below += deposit["amount"];
                    count_below += 1;
                }
                else {
                    amount_above += deposit["amount"];
                    count_above += 1;
                }
            }

            var above_div = $(document.createElement("div"));
            above_div.addClass(div_class);
            var above_span = $(document.createElement("span"));
            var fast_link_above = make_new_quick_link(price, 0, expiry_date);
            above_span.text("฿" + amount_above.round(8) + " (" + count_above + ")");
            above_div.append(above_span);
            above_div.append(fast_link_above);
            above_cell.append(above_div);
            

            var below_div = $(document.createElement("div"));
            below_div.addClass(div_class);
            var below_span = $(document.createElement("span"));
            var fast_link_below = make_new_quick_link(price, 1, expiry_date);
            below_span.text("฿" + amount_below.round(8) + " (" + count_below + ")");
            below_div.append(below_span);
            below_div.append(fast_link_below);
            below_cell.append(below_div);
        }
        
        return row;
    }

    function make_new_quick_link(price, lt, expiry_date) {
        var two_hours_away = new Date(new Date().getTime() + 2*60*60*1000);
        expiry_date_is_more_than_two_hours_away = expiry_date > two_hours_away;
        
        var link = $(document.createElement("a"));
        if (expiry_date_is_more_than_two_hours_away) {
            var url = "#price=" + price + "&lt=" + lt + "&time=" + expiry_date.getTime()
            link.attr("href", url);
            link.addClass("fast_populate_link");
            link.click(populate_values_from_fragment);
            link.text("+");
        }
        return link;
    }

    function reset_deposit_address() {
        $("#deposit_address").text("");
    }

    function populate_values_from_fragment(e) {
        if(e) {
            location.hash = e.target.href.split("#")[1];
        }
        var param_str = location.hash.replace("#","");
        var params_array = param_str.split("&");
        var params = {}
        for (var i=0,len=params_array.length; i<len; i++) {
            var param = params_array[i];
            var param_bits = param.split("=");
            var key = param_bits[0];
            var value = param_bits[1];
            params[key] = value;
        }
        if ("lt" in params) {
            var will_be_less_than = params["lt"] == 1;
            if (will_be_less_than) {
                $("#lt_gt_select").val("lt");
            }
            else {
                $("#lt_gt_select").val("gt");
            }
        }
        if ("price" in params) {
            var price = params["price"];
            $("#price").val(price);
        }
        else {
            $("#price").val("");
        }
        if ("time" in params) {
            var date = new Date(parseInt(params["time"]))
            $("#datetimepicker").val(date.to_datetimepicker_format());
        }
        else {
            $("#datetimepicker").val("");
        }
        $("#winning_address").focus();
        window.scrollTo(0,0);
    }
});