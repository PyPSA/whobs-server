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
    request.open('GET', '/coordinates/' + latlng['lat'] + '/' + latlng['lng'], true);
    request.onload = function () {

	// Begin accessing JSON data here
	var data = JSON.parse(this.response);
	console.log(data);

    }

    request.send();

};

function onMapClick(e) {
    process_coordinates(e.latlng);
    popup
	.setLatLng(e.latlng)
	.setContent("You clicked the map at " + e.latlng.toString())
	.openOn(mymap);
}

mymap.on('click', onMapClick);




let assumptions = {"country" : "DE",
		   "year" : 2013,
		   "wind" : true,
		   "wind_cost" : 1200,
		   "solar" : true,
		   "solar_cost" : 800,
		   "battery" : true,
		   "battery_energy_cost" : 300,
		   "battery_power_cost" : 300,
		   "hydrogen" : true,
		   "hydrogen_energy_cost" : 0.5,
		   "hydrogen_electrolyser_cost" : 750,
		   "hydrogen_electrolyser_efficiency" : 80,
		   "hydrogen_turbine_cost" : 800,
		   "hydrogen_turbine_efficiency" : 60,
		   "discount_rate" : 5};

for (let i = 0; i < Object.keys(assumptions).length; i++){
    let key = Object.keys(assumptions)[i];
    let value = assumptions[key];
    if(value == true){
	document.getElementsByName(key)[0].checked = value;
	d3.selectAll("input[name='" + key + "']").on("change", function(){
	    assumptions[key] = this.checked;
	    console.log(key,"changed to",assumptions[key]);
	});
    }
    else{
	document.getElementsByName(key)[0].value = value;
	d3.selectAll("input[name='" + key + "']").on("change", function(){
	    assumptions[key] = this.value;
	    console.log(key,"changed to",assumptions[key]);
	});
    }
};


var solveButton = d3.select("#solve-button");


var solving = false;

var jobid = "";

var timer;

// time between status polling in milliseconds
var poll_interval = 2000;

solveButton.on("click", function() {
    var button = d3.select(this);
    if (button.text() == "Solve") {
	var send_job = new XMLHttpRequest();
	send_job.open('POST', '/jobs', true);
	send_job.setRequestHeader("Content-Type", "application/json");
	send_job.onload = function () {
	    var data = JSON.parse(this.response);
	    console.log(data);
	    jobid = data["jobid"];
	    timer = setInterval(poll_result, poll_interval);
	    console.log("timer",timer,"polling every",poll_interval,"milliseconds");
	};
	send_job.send(JSON.stringify(assumptions));

	solving = true;
	button.text("Solving");
	document.getElementById("status").innerHTML="Sending job to solver";
    };
    console.log("");
});
//api.add_resource(Poll, '/poll/<jobid>')
//api.add_resource(Final, '/final/<jobid>')
//api.add_resource(Coordinates, '/coordinates/<lat>/<lng>')


function poll_result() {

    console.log("gibbon",jobid);
    var poll = new XMLHttpRequest();

    poll.open('GET', '/jobs/' + jobid, true);

    poll.onload = function () {
	let results = JSON.parse(this.response);
	status = results["status"];
	document.getElementById("status").innerHTML=status;
	console.log("status is",status);

	if(status == "Error"){
	    clearInterval(timer);
	    console.log("results:",results);
	    document.getElementById("status").innerHTML=status + ": " + results["error"];
	    solveButton.text("Solve");
	    solving = false;
	};
	if(status == "Finished"){
	    clearInterval(timer);
	    console.log("results:",results);
	    solving = false;
	    solveButton.text("Solve");
	    document.getElementById("objective").innerHTML=results["objective"];
	    document.getElementById("solar_capacity").innerHTML=results["solar_capacity"];
	    document.getElementById("wind_capacity").innerHTML=results["wind_capacity"];
	};
    };
    poll.send();
};
