
Date.prototype.pprint = function() {
    var Y = this.getUTCFullYear();
    var M = this.getUTCMonth() + 1;
    var D = this.getUTCDate();
    var h = this.getUTCHours();
    var m = this.getUTCMinutes();
    var s = this.getUTCSeconds();
    return Y + "-" + M.pad() + "-" + D.pad() + " " + h.pad() + ":" + m.pad() + ":" + s.pad() + " UTC";
}

Date.prototype.to_datetimepicker_format = function() {
    var Y = this.getUTCFullYear();
    var M = this.getUTCMonth() + 1;
    var D = this.getUTCDate();
    var h = this.getUTCHours();
    var m = this.getUTCMinutes();
    return Y + "-" + M.pad() + "-" + D.pad() + " " + h.pad() + ":" + m.pad();
}

Number.prototype.pad = function() {
    var x = this.toString();
    while(x.length < 2) {
        x = "0" + x;
    }
    return x;
}

Number.prototype.round = function(dp) {
    multiplier = Math.pow(10,dp);
    return Math.round(this*multiplier) / multiplier;
}



$.ajaxSetup({
    "cache": false,
});

$(document).ajaxError(function(event,request,settings){

    if(request.status == 302 || request.status == 12150) { //12150 for IE8 ?!
        window.location.href = request.responseText;
    }
    else if(request.status == 400) {
        $("#error").html(request.responseText);
    }
    else if(request.status == 402) {
        $("#error").html(request.responseText);
    }
    else if(request.status == 403) {
        $("#error").text(gettext("No permission to do this"));
    }
    else if(request.status == 404) {
        $("#error").text(gettext("Page or data not found")); //TODO make more humanised, less geeky
    }
    else if(request.status == 429) {
        $("#error").html(request.responseText);
    }
    else if(request.status == 0) {
        $("#error").text(gettext("Unable to access the server"));
    }
    else if(request.status == 500) {
        $("#error").text(gettext("The server produced an error"));
    }
    else {
        $("#error").text(gettext("Unknown error") + ": status " + request.status) //TODO make this better
    }
    return false;
});

