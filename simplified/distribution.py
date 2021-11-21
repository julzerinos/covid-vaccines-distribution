# Required cplex setup
# Run `python ./setup.py install` in the cplex/python application installation folder
# More details https://www.ibm.com/docs/en/SSSA5P_12.8.0/ilog.odms.cplex.help/CPLEX/GettingStarted/topics/set_up/Python_setup.html

import json
from os import name
from docplex.mp.model import Model
from docplex.mp.solution import SolveSolution
from docplex.mp.linear import LinearExpr


# Step 0 - Prepare the environment
def create_model() -> Model:
    return Model('modelDistribution')


# Step 1 - Prepare the data
def prepare_data(model: Model, objects_path='.') -> LinearExpr:

    # Data and sets ##

    with open(objects_path + "/airports.json", "r") as f:
        airports = json.load(f)
    with open(objects_path + "/vaccinationPoints.json", "r") as f:
        vaccination_points = json.load(f)
    with open(objects_path + "/warehouses.json", "r") as f:
        warehouses = json.load(f)
    with open(objects_path + "/routes.json", "r") as f:
        routes = json.load(f)

    with open(objects_path + "/trucks.json", "r") as f:
        truck_types = json.load(f)
    with open(objects_path + "/vaccines.json", "r") as f:
        vaccine_types = json.load(f)

    all_points = {}
    all_points.update(airports)
    all_points.update(warehouses)
    all_points.update(vaccination_points)

    routes_from_airports = {
        rname: route for rname, route in routes.items()
        if route['start'].startswith('A')
    }
    routes_to_vacc_points = {
        rname: route for rname, route in routes.items()
        if route['end'].startswith('U')
    }

    point_edge_lookup = {
        pname:
            {
                'in': [rname for rname, route in routes.items()
                       if route['end'] == pname],
                'out': [rname for rname, route in routes.items()
                        if route['start'] == pname],
            }
            for pname, node in all_points.items()
    }

    truck_route_combinations = {
        r + t: {'route': r, 'truck': t} for t in truck_types for r in routes
    }

    

    # Decision variables ##

    vaccine_quantities = model.integer_var_dict(
        routes, name="dvar_vaccines_per_route"
    )

    truck_routes = model.integer_var_dict(
        truck_route_combinations, name="dvar_trucks_per_route"
    )

    # Expressions ##

    # Cost of truck usage (rent + km usage)
    trucks_rent_cost = model.sum(
        amount * truck_types[truck_route_combinations[tr]['truck']]['rentCost']
        +
        routes[truck_route_combinations[tr]['route']]['distance']
        * truck_types[truck_route_combinations[tr]['truck']]['kmCost']


        for tr, amount in truck_routes.items()
    )

    # Constraints ##

    # Routes from airports can have at most the delivery amount of the airport
    for rname, route in routes_from_airports.items():
        model.add_constraint(
            vaccine_quantities[rname] <= airports[route['start']
                                                  ]['deliveryAmount'],
            ctname="ct_airport_max_" + rname
        )

    # Routes to the vaccination points must have at least the demand of the point
    for rname, route in routes_to_vacc_points.items():
        model.add_constraint(
            vaccine_quantities[rname] >= vaccination_points[route['end']]['demand'],
            ctname="ct_airport_max_" + rname
        )

    # Sum of truck capacity must be at least the amount of vaccines transported on its route
    for r in routes:
        model.add_constraint(
            model.sum(
                amount for tr, amount in truck_routes.items()
                if r in tr
            ) >= vaccine_quantities[r],
            ctname='ct_truck_capacity'
        )

    # Objective function - cost of the distribution ##

    f = trucks_rent_cost

    return f


# Step 3 - Set the objective
def set_objective(model: Model, objective_function: LinearExpr):
    model.set_objective("min", objective_function)


# Step 4 - Solve the problem
def solve_problem(model: Model) -> SolveSolution:
    solution = model.solve()
    return solution


# Step 5 - Communicate the results
def print_solution(model: Model):
    model.print_information()
    model.print_solution(print_zeros=True)


def save_solution(solution: SolveSolution):
    with open("solution.json", 'w') as f:
        f.write(solution.export_as_json_string())


# Helper functions

def route_time_for_truck(route, truck):
    return route['distance'] / truck['avgSpeed']