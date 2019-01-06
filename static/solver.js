

var parseDate = d3.timeParse("%Y-%m-%d %H:%M:00");

var formatDate = d3.timeFormat("%b %d %H:%M");


var colors = {"wind":"#3B6182",
              "solar" :"#FFFF00",
              "battery" : "#999999",
              "battery_power" : "#999999",
              "battery_energy" : "#666666",
              "hydrogen_turbine" : "red",
              "hydrogen_electrolyser" : "cyan",
              "hydrogen_energy" : "magenta",
             };


let tech_assumptions = {"2020" : {"wind_cost" : 1240,
				  "solar_cost" : 750,
				  "battery_energy_cost" : 300,
				  "battery_power_cost" : 300,
				  "hydrogen_energy_cost" : 0.5,
				  "hydrogen_electrolyser_cost" : 900,
				  "hydrogen_electrolyser_efficiency" : 75,
				  "hydrogen_turbine_cost" : 800,
				  "hydrogen_turbine_efficiency" : 60,

				 },
			"2030" : {"wind_cost" : 1182,
				  "solar_cost" : 600,
				  "battery_energy_cost" : 200,
				  "battery_power_cost" : 200,
				  "hydrogen_energy_cost" : 0.5,
				  "hydrogen_electrolyser_cost" : 700,
				  "hydrogen_electrolyser_efficiency" : 80,
				  "hydrogen_turbine_cost" : 800,
				  "hydrogen_turbine_efficiency" : 60,
				 },
			"2050" : {"wind_cost" : 1075,
				  "solar_cost" : 425,
				  "battery_energy_cost" : 100,
				  "battery_power_cost" : 100,
				  "hydrogen_energy_cost" : 0.5,
				  "hydrogen_electrolyser_cost" : 500,
				  "hydrogen_electrolyser_efficiency" : 80,
				  "hydrogen_turbine_cost" : 800,
				  "hydrogen_turbine_efficiency" : 60,
				 }
		       };

let assumptions = {"country" : "GB",
		   "load" : 100,
		   "year" : 2013,
		   "frequency" : 3,
		   "wind" : true,
		   "solar" : true,
		   "battery" : true,
		   "hydrogen" : true,
		   "discount_rate" : 5,
		  };

let default_tech_scenario = "2030";

for (let i = 0; i < Object.keys(tech_assumptions[default_tech_scenario]).length; i++){
    let key = Object.keys(tech_assumptions[default_tech_scenario])[i];
    assumptions[key] = tech_assumptions[default_tech_scenario][key];
};


d3.select("#tech_scenario").on("change", function(){
    let scenario = this.value;
    console.log("tech scenario change to ",scenario);
    for (let i = 0; i < Object.keys(tech_assumptions[scenario]).length; i++){
	let key = Object.keys(tech_assumptions[scenario])[i];
	let value = tech_assumptions[scenario][key];
	assumptions[key] = value;
	document.getElementsByName(key)[0].value = value;
    };
});



//state variable for graph period
let period = "year";

var d = 10;

var results = {};

// Centered on Frankfurt
var mymap = L.map('mapid').setView([50.11, 8.68], 3);

L.tileLayer('https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?access_token={accessToken}', {
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, <a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
    maxZoom: 18,
    id: 'mapbox.streets',
    accessToken: 'pk.eyJ1IjoibndvcmJtb3QiLCJhIjoiY2prbWxibTUyMjZsMDNwcGp2bHR3OWZsaSJ9.MgSprgR6BEbBLXl5rPvXvQ'
}).addTo(mymap);





// See https://oramind.com/country-border-highlighting-with-leaflet-js/
d3.json("static/ne_50m_admin_0_countries_simplified_europe.json", function (json){
    function style(feature) {
	function getColor(f){
	    if(feature.properties.iso_a2 == assumptions["country"]){
		return "red";
	    } else {
		return "blue";
	    };
	};
	return {
	    fillColor: getColor(feature),
	    weight: 1,
	    opacity: 0.4,
	    color: getColor(feature),
	    fillOpacity: 0.3
	};
    };
    geojson = L.geoJson(json, {
	onEachFeature: onEachFeature,
	style : style
    }).addTo(mymap);

    function onEachFeature(feature, layer){
	layer.on({
	    click : onCountryClick,
	    mouseover : onCountryMouseOver,
	    mouseout : onCountryMouseOut
	});
    }
});



function onCountryMouseOut(e){
    geojson.resetStyle(e.target);
}

function onCountryClick(e){

    //console.log(e.target.feature.properties.name,e.target.feature.properties.iso_a2);

    assumptions["country"] = e.target.feature.properties.iso_a2;
    document.getElementsByName("country")[0].value = assumptions["country"];
    console.log("country changed to",assumptions["country"]);

    geojson.eachLayer(function(t,i){ geojson.resetStyle(t)});
    //console.log(t.feature.properties.name)})
}

/**
 * Callback for when a country is highlighted. Will take care of the ui aspects, and it will call
 * other callbacks after done.
 * @param e
 */
function onCountryMouseOver(e){

    var layer = e.target;

    layer.setStyle({
	weight: 2,
	color: '#666',
	dashArray: '',
	fillOpacity: 0.7
    });

    if (!L.Browser.ie && !L.Browser.opera) {
	layer.bringToFront();
    }
}



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

var jobid = "";

var timer;
var timeout;

// time between status polling in milliseconds
var poll_interval = 2000;

// time out for polling if it doesn't finish after 10 minutes
// Shouldn't be divisible by poll_interval
var poll_timeout = 10*60*1000 + poll_interval/2;


solveButton.on("click", function() {
    var button = d3.select(this);
    if (button.text() == "Solve") {
	clear_results();
	var send_job = new XMLHttpRequest();
	send_job.open('POST', '/jobs', true);
	send_job.setRequestHeader("Content-Type", "application/json");
	send_job.onload = function () {
	    var data = JSON.parse(this.response);
	    jobid = data["jobid"];
	    console.log("Jobid:",jobid);
	    timer = setInterval(poll_result, poll_interval);
	    console.log("timer",timer,"polling every",poll_interval,"milliseconds");
	    timeout = setTimeout(poll_kill, poll_timeout);
	};
	send_job.send(JSON.stringify(assumptions));

	button.text("Solving");
	button.attr("id","solve-button-busy");
	document.getElementById("status").innerHTML="Sending job to solver";
    };
});
//api.add_resource(Poll, '/poll/<jobid>')
//api.add_resource(Final, '/final/<jobid>')
//api.add_resource(Coordinates, '/coordinates/<lat>/<lng>')


function poll_result() {

    var poll = new XMLHttpRequest();

    poll.open('GET', '/jobs/' + jobid, true);

    poll.onload = function () {
	results = JSON.parse(this.response);
	status = results["status"];
	document.getElementById("status").innerHTML=status;
	console.log("status is",status);

	if(status == "Error"){
	    clearInterval(timer);
	    clearTimeout(timeout);
	    console.log("results:",results);
	    document.getElementById("status").innerHTML=status + ": " + results["error"];
	    solveButton.text("Solve");
	    solveButton.attr("id","solve-button");
	};
	if(status == "Finished"){
	    clearInterval(timer);
	    clearTimeout(timeout);
	    console.log("results:",results);
	    solveButton.text("Solve");
	    solveButton.attr("id","solve-button");
	    display_results();
	};
    };
    poll.send();
};


function poll_kill() {
    clearInterval(timer);
    solveButton.text("Solve");
    solveButton.attr("id","solve-button");
    document.getElementById("status").innerHTML="Error: Timed out";
};




assets = ["solar","wind","battery_power",
	      "battery_energy","hydrogen_electrolyser",
	      "hydrogen_turbine","hydrogen_energy"]

vre = ["solar","wind"]

function clear_results(){
    document.getElementById("results_assumptions").innerHTML="";
    document.getElementById("average_cost").innerHTML="";
    document.getElementById("load").innerHTML="";
    for (let i = 0; i < assets.length; i++){
	document.getElementById(assets[i] + "_capacity").innerHTML="";
	if(!assets[i].includes("energy")){
	    document.getElementById(assets[i] + "_cf_used").innerHTML="";
	};

    };
    for (let i = 0; i < vre.length; i++){
	document.getElementById(assets[i] + "_cf_available").innerHTML="";
	document.getElementById(assets[i] + "_curtailment").innerHTML="";
    };
    d3.select("#power").selectAll("g").remove();
    d3.select("#average_cost_graph").selectAll("g").remove();
    d3.select("#power_capacity_graph").selectAll("g").remove();
    d3.select("#energy_capacity_graph").selectAll("g").remove();
    d3.select("#energy_graph").selectAll("g").remove();

};


function display_results(){
    document.getElementById("results_assumptions").innerHTML=" for country " + results["assumptions"]["country"] + " in year " + results["assumptions"]["year"];
    document.getElementById("average_cost").innerHTML=results["average_cost"].toFixed(1);
    document.getElementById("load").innerHTML=results["assumptions"]["load"].toFixed(1);

    for (let i = 0; i < assets.length; i++){
	document.getElementById(assets[i] + "_capacity").innerHTML=Math.abs(results[assets[i] + "_capacity"].toFixed(1));
	if(!assets[i].includes("energy")){
	    document.getElementById(assets[i] + "_cf_used").innerHTML=Math.abs((results[assets[i] + "_cf_used"]*100)).toFixed(1);
	};
    };
    for (let i = 0; i < vre.length; i++){
	document.getElementById(assets[i] + "_cf_available").innerHTML=Math.abs((results[assets[i] + "_cf_available"]*100)).toFixed(1);
	document.getElementById(assets[i] + "_curtailment").innerHTML=Math.abs((results[assets[i] + "_curtailment"]*100)).toFixed(1);
    };



    for(var j=0; j < results.snapshots.length; j++) {
	results.snapshots[j] = parseDate(results.snapshots[j]);
    };

    draw_power_graph();
    draw_cost_stack();
    draw_power_capacity_stack();
    draw_energy_capacity_stack();
    draw_energy_stack();
};


//graph parameters
var x = {};
var y = {};
var ymin = {};
var ymax = {};


function draw_power_graph(){

    var name = "time";

    let snapshots = results["snapshots"];
    let selection = [...Array(results["snapshots"].length).keys()];

    if(period != "year"){
	let week = parseInt(period.slice(4));
	selection = selection.slice((week-1)*7*24/results["assumptions"]["frequency"],week*7*24/results["assumptions"]["frequency"]);
	snapshots = snapshots.slice((week-1)*7*24/results["assumptions"]["frequency"],week*7*24/results["assumptions"]["frequency"]);
    };

    // Inspired by https://bl.ocks.org/mbostock/3885211

    var svgGraph = d3.select("#power"),
	margin = {top: 20, right: 20, bottom: 30, left: 50},
	width = svgGraph.attr("width") - margin.left - margin.right,
	height = svgGraph.attr("height") - margin.top - margin.bottom;

    // remove existing
    svgGraph.selectAll("g").remove();
    x[name] = d3.scaleTime().range([0, width]),
	y[name] = d3.scaleLinear().range([height, 0]);

    data = [];

    // Custom version of d3.stack

    var previous = new Array(selection.length).fill(0);

    for (var j = 0; j < results["positive"].columns.length; j++){
	var item = [];
	for (var k = 0; k < selection.length; k++){
	    item.push([previous[k], previous[k] + results["positive"]["data"][selection[k]][j]]);
	    previous[k] = previous[k] + results["positive"]["data"][selection[k]][j];
	    }
	data.push(item);
    }
    var previous = new Array(selection.length).fill(0);

    for (var j = 0; j < results["negative"].columns.length; j++){
	var item = [];
	for (var k = 0; k < selection.length; k++){
	    item.push([-previous[k] - results["negative"]["data"][selection[k]][j],-previous[k]]);
	    previous[k] = previous[k] + results["negative"]["data"][selection[k]][j];
	    }
	data.push(item);
    }

    ymin[name] = 0, ymax[name] = 0;
    for (var k = 0; k < selection.length; k++){
	if(data[results["positive"].columns.length-1][k][1] > ymax[name]){ ymax[name] = data[results["positive"].columns.length-1][k][1];};
	if(data[results["positive"].columns.length+results["negative"].columns.length-1][k][0] < ymin[name]){ ymin[name] = data[results["positive"].columns.length+results["negative"].columns.length-1][k][0];};
    };

    var area = d3.area()
        .x(function(d, i) { return x[name](snapshots[i]); })
        .y0(function(d) { return y[name](d[0]); })
        .y1(function(d) { return y[name](d[1]); });


    var g = svgGraph.append("g")
        .attr("transform", "translate(" + margin.left + "," + margin.top + ")");


    x[name].domain(d3.extent(snapshots));
    y[name].domain([ymin[name],ymax[name]]);

    var layer = g.selectAll(".layer")
        .data(data)
        .enter().append("g")
        .attr("class", "layer");

    layer.append("path")
        .attr("class", "area")
        .style("fill", function(d, i) {if(i < results["positive"].color.length){ return results["positive"].color[i];} else{return results["negative"].color[i-results["positive"].color.length];} })
        .attr("d", area);

    g.append("g")
        .attr("class", "axis axis--x")
        .attr("transform", "translate(0," + height + ")")
        .call(d3.axisBottom(x[name]));

    g.append("g")
        .attr("class", "axis axis--y")
        .call(d3.axisLeft(y[name]));

    var label = svgGraph.append("g").attr("class", "y-label");

    // text label for the y axis
    label.append("text")
        .attr("transform", "rotate(-90)")
        .attr("y", 0)
        .attr("x",0 - (height / 2))
        .attr("dy", "1em")
        .style("text-anchor", "middle")
        .text("Power [MW]");
};




function draw_cost_stack(){

    let data = [];
    let color = [];

    for(let i=0; i < assets.length; i++){
	data.push(results[assets[i]+"_cost"]/results["assumptions"]["load"]);
	color.push(colors[assets[i]]);
    };

    draw_stack(data, color, "Breakdown of average system cost [EUR/MWh]", "#average_cost_graph");
}


function draw_power_capacity_stack(){

    let data = [];
    let color = [];

    for(let i=0; i < assets.length; i++){
	if(!assets[i].includes("energy")){
	    data.push(results[assets[i]+"_capacity"]);
	    color.push(colors[assets[i]]);
	};
    };

    draw_stack(data, color, "Power capacity [MW]", "#power_capacity_graph");
}



function draw_energy_capacity_stack(){

    let data = [];
    let color = [];

    for(let i=0; i < assets.length; i++){
	if(assets[i].includes("energy")){
	    data.push(results[assets[i]+"_capacity"]/1000.);
	    color.push(colors[assets[i]]);
	};
    };

    draw_stack(data, color, "Energy storage capacity [GWh]", "#energy_capacity_graph");
}


function draw_energy_stack(){

    let data = [];
    let color = [];

    for(let i=0; i < assets.length; i++){
	if(assets[i] + "_used" in results){
	    data.push(results[assets[i]+"_used"]);
	    color.push(colors[assets[i]]);
	};
    };

    draw_stack(data, color, "Average power dispatch [MW]", "#energy_graph");
}


function draw_stack(data, color, ylabel, svgName){

    // Inspired by https://bl.ocks.org/mbostock/3885211 and
    // https://bl.ocks.org/mbostock/1134768


    let totals = [0.];

    for(let i=0; i < data.length; i++){
	totals.push(totals[i] + data[i]);
    };

    let svgGraph = d3.select(svgName),
	margin = {top: 20, right: 20, bottom: 30, left: 50},
	width = svgGraph.attr("width") - margin.left - margin.right,
	height = svgGraph.attr("height") - margin.top - margin.bottom;

    // remove existing
    svgGraph.selectAll("g").remove();
    let x = d3.scaleLinear().range([0, width]);
    let y = d3.scaleLinear().range([height, 0]);

    x.domain([0,1]);
    y.domain([0,totals[totals.length-1]]).nice();

    var g = svgGraph.append("g")
        .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    var layer = g.selectAll("rect")
        .data(data)
        .enter().append("rect")
	.attr("x", x(0.1))
        .attr("y", function(d,i) { return y(totals[i+1]);})
        // following abs avoids rect with negative height e.g. -1e10
	.attr("height", function(d,i) { return Math.abs((y(totals[i]) - y(totals[i+1])).toFixed(2)); })
    	.attr("width", x(0.8))
        .style("fill", function(d, i) { return color[i];});

    //g.append("g")
    //    .attr("class", "axis axis--x")
    //    .attr("transform", "translate(0," + height + ")")
    //    .call(d3.axisBottom(x));

    g.append("g")
        .attr("class", "axis axis--y")
        .call(d3.axisLeft(y));

    var label = svgGraph.append("g").attr("class", "y-label");

    // text label for the y axis
    label.append("text")
        .attr("transform", "rotate(-90)")
        .attr("y", 0)
        .attr("x",0 - (height / 2))
        .attr("dy", "1em")
        .style("text-anchor", "middle")
        .text(ylabel);

    var label = svgGraph.append("g").attr("class", "column-total")
        .attr("transform", "translate(" + margin.left + "," + margin.top + ")");


    // text label for the y axis
    label.append("text")
        .attr("y", y(totals[totals.length-1])-20)
        .attr("x",x(0.5))
        .attr("dy", "1em")
        .style("text-anchor", "middle")
        .text(totals[totals.length-1].toFixed(1));



};



//Legend
let legendSVG = d3.select("#legend")
    .append("svg")
    .attr("width",180)
    .attr("height",assets.length*20);

let legend = legendSVG.selectAll("g")
    .data(assets)
    .enter()
    .append("g")
    .attr("transform", function (d, i) {  return "translate(0," + (5 + i * 20) + ")" });

legend.append("rect")
    .attr("x",0)
    .attr("y",0)
    .attr("width", 10)
    .attr("height", 10)
    .style("fill", function (d, i) { return colors[d] });

legend.append("text")
    .attr("x",20)
    .attr("y",10)
    .text(function (d) { return d.replace("_"," ")});





let selectPeriod = d3.select("#jumpmenu").selectAll("option")
    .data([...Array(53).keys()])
    .enter()
    .append("option")
    .attr("value", function (d, i) {  return "week"+d })
    .text( function (d, i) {  return "week "+d });

d3.select("#jumpmenu").on("change", function(){
    period = this.value;
    console.log("period change to ",period);
    draw_power_graph();
});



// load initial results for assumptions["country"]
d3.json("static/results-initial.json", function(r){
    results = r;
    console.log(results);
    display_results();
});
