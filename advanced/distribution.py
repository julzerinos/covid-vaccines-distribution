# Required cplex setup
#   Run `python ./setup.py install` in the
#   cplex/python application installation folder
# More details https://www.ibm.com/docs/en/SSSA5P_12.8.0/ilog.odms.cplex.help/CPLEX/GettingStarted/topics/set_up/Python_setup.html

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
        v + p + a: {'vaccine': v, 'point': p, 'airport': a}
        for v in vaccine_types
        for p in vaccination_points
        for a in airports
    }

    route_vaccine_point_combinations = {
        r + v + p + a: {'route': r, 'vaccine': v, 'point': p, 'airport': a}
        for v in vaccine_types for p in vaccination_points for a in airports for r in routes
    }

    vaccine_point_routes = {
        vpaname: [
            rvpa['route']
            for rvpa in route_vaccine_point_combinations.values()
            if rvpa['airport'] == vpa['airport']
            and rvpa['point'] == vpa['point']
            and rvpa['vaccine'] == vpa['vaccine']
        ] for vpaname, vpa in vaccine_point_combinations.items()
    }

    truck_route_times = {
        r + t: route_time_for_truck(route, truck)
        for t, truck in truck_types.items()
        for r, route in routes.items()
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
            for vpraname, amount in vaccine_point_quantities.items()
            if route_vaccine_point_combinations[vpraname]['route'] == r
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

    # Time taken for a vaccine to travel from an airport to a vaccination point
    vaccine_travel_times = {
        vpaname: model.sum(
            model.max(
                model.min(amount, 1) * truck_route_times[tr]
                for tr, amount in truck_routes.items()
                if truck_route_combinations[tr]['route'] == r
            )
            for r in vparoutes
        )
        for vpaname, vparoutes in vaccine_point_routes.items()
    }

    # Constraints ##

    # Vaccine travel time is lower or equal to its travel lifetime
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
                vaccine_point_quantities[rvpaname]
                for rvpaname, rvpa in route_vaccine_point_combinations.items()
                if rvpa['airport'] == pname
                and rvpa['route'] in point_edge_lookup[pname]['out']
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
                vaccine_point_quantities[r + vpaname]
                for r in point_edge_lookup[pname]['in']
                for vpaname, vpa in vaccine_point_combinations.items()
                if vpa['point'] == pname
            )
            >=
            point['demand'],
            ctname="ct_airport_max_" + pname
        )

    # For warehouse points, incoming vaccines should be equal to outgoing
    #   for those specific vaccine destinations
    for w in warehouses:
        warehouse_routes = point_edge_lookup[w]
        for vpaname in vaccine_point_combinations:
            model.add_constraint(
                model.sum(
                    vaccine_point_quantities[r + vpaname]
                    for r in warehouse_routes['in']
                )
                ==
                model.sum(
                    vaccine_point_quantities[r + vpaname]
                    for r in warehouse_routes['out']
                )
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

    # Amount of point destined routes from airports have to be equal
    for aname in airports:
        model.add_constraint(
            model.sum(
                vaccine_point_quantities[rvpaname]
                for rvpaname, rvpa in route_vaccine_point_combinations.items()
                if rvpa['route'] in point_edge_lookup[aname]['out']
                and rvpa['airport'] == aname
            )
            ==
            model.sum(
                vaccine_point_quantities[rvpaname]
                for ppname in vaccination_points
                for rvpaname, rvpa in route_vaccine_point_combinations.items()
                if rvpa['route'] in point_edge_lookup[ppname]['in']
                and rvpa['airport'] == aname
            ),
            ctname='ct_vaccine_source_types_equal'
        )

    # Amount of airport sourced routes to points have to be equal
    for vname in vaccination_points:
        model.add_constraint(
            model.sum(
                vaccine_point_quantities[rvpaname]
                for rvpaname, rvpa in route_vaccine_point_combinations.items()
                if rvpa['route'] in point_edge_lookup[vname]['in']
                and rvpa['point'] == vname
            )
            ==
            model.sum(
                vaccine_point_quantities[rvpaname]
                for aaname in airports
                for rvpaname, rvpa in route_vaccine_point_combinations.items()
                if rvpa['route'] in point_edge_lookup[aaname]['out']
                and rvpa['point'] == vname
            ),
            ctname="ct_vaccine_dest_types_equal"
        )

    # Objective function - cost of the distribution ##

    f = trucks_rent_cost

    return f, [
        lambda: print(
            [[aname, a.solution_value] for aname, a in vaccine_travel_times.items()])
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
