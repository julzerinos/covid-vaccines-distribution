# Required cplex setup
#   Run `python ./setup.py install` in the
#   cplex/python application installation folder
# More details https://www.ibm.com/docs/en/SSSA5P_12.8.0/ilog.odms.cplex.help/CPLEX/GettingStarted/topics/set_up/Python_setup.html # noqa: E501

import json
from docplex.mp.model import Model
from docplex.mp.solution import SolveSolution
from docplex.mp.linear import LinearExpr


# Step 0 - Prepare the environment
def create_model() -> Model:
    return Model('model_distribution')


# Step 1 - Prepare the data
def prepare_data(model: Model, objects_path='.') -> LinearExpr:

    # Data and sets ##

    with open(objects_path + "/model.json", "r") as f:
        model_objects = json.load(f)
        airports = model_objects['airports']
        vaccination_points = model_objects['vaccinationPoints']
        warehouses = model_objects['warehouses']
        routes = model_objects['routes']
        truck_types = model_objects['trucks']
        vaccine_types = model_objects['vaccines']

    all_points = {}
    all_points.update(airports)
    all_points.update(warehouses)
    all_points.update(vaccination_points)

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

    vaccine_point_combinations = {
        v + p: {'vaccine': v, 'point': p} for v in vaccine_types for p in vaccination_points
    }

    route_vaccine_point_combinations = {
        r + vp: {'route': r, 'vaccine_point': vp} for vp in vaccine_point_combinations for r in routes
    }

    # Decision variables ##

    vaccine_point_quantities = model.integer_var_dict(
        route_vaccine_point_combinations, name='dvar_vaccine_point_quantity_per_route'
    )

    truck_routes = model.integer_var_dict(
        truck_route_combinations, name="dvar_trucks_per_route"
    )

    # Expressions ##

    # Total number of vaccines on a route
    vaccine_quantities = {
        r: model.sum(
            amount
            for vprname, amount in vaccine_point_quantities.items()
            if route_vaccine_point_combinations[vprname]['route'] == r
        ) for r in routes
    }

    # Cost of truck usage (rent + km usage)
    trucks_rent_cost = model.sum(
        amount * truck_types[truck_route_combinations[tr]['truck']]['rentCost']
        +
        amount * routes[truck_route_combinations[tr]['route']]['distance']
        * truck_types[truck_route_combinations[tr]['truck']]['kmCost']

        for tr, amount in truck_routes.items()
    )

    # Travel times of each vaccine source-destination type
    vaccine_travel_times = {
        vpname: model.sum(
            model.min(vaccine_point_quantities[rvpname], 1) *
            route_time_for_truck(routes[rvp['route']], truck_types["V1"])
            for rvpname, rvp in route_vaccine_point_combinations.items()
            if rvp['vaccine_point'] == vpname
        ) for vpname in vaccine_point_combinations
    }

    # Constraints ##

    for vpname, vp in vaccine_point_combinations.items():
        model.add_constraint(
            vaccine_travel_times[vpname]
            <=
            vaccine_types[vp['vaccine']]['lifetime'],
            ctname="ct_vaccine_travel_time"
        )

    # Routes from airports can have at most the delivery amount of the airport
    #   of any vaccine type
    for pname, point in airports.items():
        model.add_constraint(
            model.sum(
                vaccine_quantities[r] for r in point_edge_lookup[pname]['out']
            )
            <=
            point['deliveryAmount'],
            ctname="ct_airport_max_" + pname
        )

    # Sum of routes to the vaccination points must have
    #   at least the demand of the point (of vaccines destined for that point)
    for pname, point in vaccination_points.items():
        model.add_constraint(
            model.sum(
                vaccine_point_quantities[vprname]
                for vprname, vpr in route_vaccine_point_combinations.items()
                if vpr['route'] in point_edge_lookup[pname]['in']
                and vaccine_point_combinations[vpr['vaccine_point']]['point'] == pname
            ) >= point['demand'],
            ctname="ct_airport_max_" + pname
        )

    # Sum of truck capacity must be at least the amount of vaccines
    #   transported on its route (of any vaccine destination)
    for r in routes:
        model.add_constraint(
            model.sum(
                amount *
                truck_types[
                    truck_route_combinations[tr]['truck']
                ]['maxCapacity']
                for tr, amount in truck_routes.items()
                if truck_route_combinations[tr]['route'] == r
            )
            >= vaccine_quantities[r],
            ctname='ct_truck_capacity_at_least' + r
        )

    # TODO: for paths to each next point (warehouse, point) find min time then sum up (expression)
    # Vaccines must make it to the vaccination points in time smaller than
    # their travel lifetime
    # for trname, tr in truck_route_combinations.items():
    #     for vname, v in vaccine_types.items():
    #         model.add_constraint(
    #             truck_routes[trname]
    #             * route_time_for_truck(
    #                     routes[tr['route']], truck_types[tr['truck']]
    #                 )
    #             <= truck_routes[trname] * v['lifetime'],
    #             ctname='ct_vaccine_lifetime' + trname + vname
    #         )

    # For warehouse points, incoming vaccines should be equal to outgoing
    #   for those specific vaccine destinations
    for w in warehouses:
        for vp in vaccine_point_combinations:
            warehouse_routes = point_edge_lookup[w]
            model.add_constraint(
                model.sum(
                    vaccine_point_quantities[r + vp] for r in warehouse_routes['in']
                )
                ==
                model.sum(
                    vaccine_point_quantities[r + vp] for r in warehouse_routes['out']
                )
            )

    # Objective function - cost of the distribution ##

    f = trucks_rent_cost

    return f, [
        lambda: print([f"{aname}, {a.solution_value}" for aname,
                      a in vaccine_quantities.items()]),
        lambda: print([f"{aname}, {a.solution_value}" for aname,
                       a in vaccine_travel_times.items()]),
    ]


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


def save_solution(solution: SolveSolution, test_path='.'):
    with open(test_path + "/solution.json", 'w') as f:
        f.write(solution.export_as_json_string())


# Helper functions

def route_time_for_truck(route, truck):
    if truck['avgSpeed'] == 0:
        return 10e100

    return route['distance'] / truck['avgSpeed']
