function highlight(e) {
    $("." + e.className).css("background-color", "#FF9");
}

function unhighlight(e) {
    $("." + e.className).css("background-color", "");
}