    var d = 10;
    var mymap = L.map('mapid').setView([51.505, -0.09], 13);

    L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token={accessToken}', {
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, <a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
    maxZoom: 18,
    id: 'mapbox.streets',
    accessToken: 'pk.eyJ1IjoibndvcmJtb3QiLCJhIjoiY2prbWxibTUyMjZsMDNwcGp2bHR3OWZsaSJ9.MgSprgR6BEbBLXl5rPvXvQ'
    }).addTo(mymap);

    var marker = L.marker([51.5, -0.09]).addTo(mymap);

    var circle = L.circle([51.508, -0.11], {
    color: 'red',
    fillColor: '#f03',
    fillOpacity: 0.5,
    radius: 500
    }).addTo(mymap);

    var polygon = L.polygon([
    [51.509, -0.08],
    [51.503, -0.06],
    [51.51, -0.047]
    ]).addTo(mymap);

    marker.bindPopup("<b>Hello world!</b><br>I am a badass popup.").openPopup();
    circle.bindPopup("I am a circle.");
    polygon.bindPopup("I am a polygon.");

    var popup = L.popup();

    function process_coordinates(latlng){
    console.log("lat",latlng["lat"]);
    console.log("lng",latlng["lng"]);
    var request = new XMLHttpRequest();
    request.open('GET', 'http://127.0.0.1:5002/coordinates/' + latlng['lat'] + '/' + latlng['lng'], true);
    request.onload = function () {

    // Begin accessing JSON data here
      var data = JSON.parse(this.response);
      console.log(data);

    }

    request.send();

    }

    function onMapClick(e) {
    process_coordinates(e.latlng);
    popup
    .setLatLng(e.latlng)
    .setContent("You clicked the map at " + e.latlng.toString())
    .openOn(mymap);
    }

    mymap.on('click', onMapClick);



// state variables
var asset_status = {};

var assets = ["wind","solar","h2","battery"];


var asset_status = {};

for (var i = 0; i < assets.length; i++){
    asset_status[assets[i]] = true;
}

var asset_items = ["wind","solar","battery_kwh","battery_kw","h2_electrolysis","h2_storage","h2_turbine"];
var asset_default_costs = [1200,800,300,300,750,0.5,800];

var asset_costs = {};

for (var i = 0; i < asset_items.length; i++){
    asset_costs[asset_items[i]] = asset_default_costs[i];
}


d3.select("#tech_checkboxes").selectAll("input").data(assets)
    .enter()
    .append("input")
    .attr("type","checkbox")
    .attr("name", function (d,i) { return d })
    .text(function (d,i) { return d})
    .on("click", function (d,i) { console.log(d,"status changed to",this.checked)})
    .append("label")
    .attr("for", function (d,i) { return d});

d3.select("#tech_costs").selectAll("input").data(asset_items)
    .enter()
    .append("input")
    .attr("type","number")
    .attr("name", function (d,i) { return d })
    .attr("value", function (d,i) { return asset_default_costs[i] })
    .text(function (d,i) { return d})
    .on("change", function (d,i) { console.log(d,"cost changed to",this.value);
				   asset_costs[d] = this.value;
				 })
    .append("label")
    .attr("for", function (d,i) { return d});

d3.selectAll("input[name='wind']").on("change", function(){
    console.log("changed value",this.value,"changed checked",this.checked);
    //scenario = this.value;
});


d3.selectAll("input[name='wind-cost']").on("change", function(){
    console.log("changed value",this.value,"changed checked",this.checked);
    //scenario = this.value;
});



var country = "FR";

d3.selectAll("input[name='country']").on("change", function(){
    country = this.value;
    console.log("changed country to",country);
    //scenario = this.value;
});






var solveButton = d3.select("#solve-button");


var solving = false;

var jobid = "";

var timer;

// time between status polling in milliseconds
var poll_interval = 5000;

solveButton.on("click", function() {
	var button = d3.select(this);
    if (button.text() == "Solve") {
	var request = new XMLHttpRequest();
	request.open('GET', 'http://127.0.0.1:5002/solve/' + country + '/' + asset_costs["wind"], true);

	request.onload = function () {

	    // Begin accessing JSON data here
	    var data = JSON.parse(this.response);
	    console.log(data);
	    jobid = data["jobid"];
	    timer = setInterval(poll_result, poll_interval);
	    console.log(timer,poll_interval);
	}

	request.send();

	solving = true;
	button.text("Solving");
	document.getElementById("status").innerHTML="Sending job to solver";
    } else {
    }
    console.log("");
});
//api.add_resource(Poll, '/poll/<jobid>')
//api.add_resource(Final, '/final/<jobid>')
//api.add_resource(Coordinates, '/coordinates/<lat>/<lng>')


function poll_result() {

    console.log("gibbon",jobid);
    var poll = new XMLHttpRequest();

    poll.open('GET', 'http://127.0.0.1:5002/poll/' + jobid, true);

    poll.onload = function () {
	var status = JSON.parse(this.response);
	document.getElementById("status").innerHTML=status;
	console.log(status);
	//if finished, then get result

	if(status == "Finished"){
	    clearInterval(timer);
	    var final = new XMLHttpRequest();
	    final.open('GET', 'http://127.0.0.1:5002/final/' + jobid, true);

	    final.onload = function () {
		var results = JSON.parse(this.response);
		console.log(results);
		solving = false;
		solveButton.text("Solve");
		document.getElementById("objective").innerHTML=results["objective"];
		document.getElementById("solar_capacity").innerHTML=results["solar_cap"];
	    };
	    final.send();
	}
    };
    poll.send();
};
