from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
import re
import json
import requests
import logging

import azure.functions as func

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    get_edamam_data()

    return func.HttpResponse(f"Done")

current_products_names = []
current_recipes_directions = []
quantity_words = ["tablespoon", "cup", "tablespoons", "cups", "tbsp", "handful", "ounce", "pound", "pounds", "teaspoons", "teaspoon", "tsp", "package", "plus", "very", "warm", "large", "pieces", "fresh", "slices", "small", "freshly", "percent", "pack", "can", "chunky", "allpurpose", "goz", "mlfl", "chopped"]
Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    image_url = Column(String)

class Recipe(Base):
    __tablename__ = 'recipes'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    directions = Column(String)

class ProductRecipe(Base):
    __tablename__ = 'products_recipes'
    products_id = Column(Integer, primary_key=True)
    recipes_id = Column(Integer, primary_key=True)

def get_edamam_data():
    global current_recipes_directions
    global current_products_names

    engine = create_engine("mysql+pymysql://<CONNECTION STRING>")
    Session = sessionmaker(bind=engine)
    session = Session()
    current_products = session.query(Product).all()
    current_recipes = session.query(Recipe).all()

    current_products_names = [product.name for product in current_products]
    current_recipes_directions = [recipe.directions for recipe in current_recipes]

    edamam_url = "<EDAMAM URL>"
    http_response = requests.get(edamam_url)
    response_data = json.loads(http_response.content)
    
    for hit in response_data["hits"]:
        if is_new_recipe(hit["recipe"]["url"]):
            current_products = session.query(Product).all()
            current_products_names = [product.name for product in current_products]
            ingredients_list = set()
            for ingredient in hit["recipe"]["ingredientLines"]:
                ingredient_clear_name = clear_name(ingredient)
                if len(ingredient_clear_name) > 0:
                    ingredients_list.add(ingredient_clear_name)

            ingredients_ids = []
            for single_ingredient in ingredients_list:
                if single_ingredient not in current_products_names:
                    image_url = get_image_url(single_ingredient)
                    if image_url is not None:
                        new_product = Product(name = single_ingredient, description = get_nutrient_information(single_ingredient), image_url = image_url)
                        session.add(new_product)
                        session.flush()
                        ingredients_ids.append(new_product.id)
                else:
                    product = session.query(Product).filter(Product.name == single_ingredient).first()
                    ingredients_ids.append(product.id)

            new_recipe = Recipe(title = hit["recipe"]["label"], directions = hit["recipe"]["url"])
            session.add(new_recipe)
            session.flush()

            for single_id in ingredients_ids:
                new_product_recipe = ProductRecipe(products_id = single_id, recipes_id = new_recipe.id)
                session.add(new_product_recipe)

            session.commit()

    return ingredients_list

def is_new_recipe(recipe_url):
    global current_recipes_directions

    return recipe_url not in current_recipes_directions

def get_image_url(ingredient_name):
    bing_url = f"<BING URL>"
    #pixels_url = f"<PIXELS URL>"
    headers = {}
    #headers["Authorization"] = "<PIXELS TOKEN>"
    headers["Ocp-Apim-Subscription-Key"] = "<BING TOKEN>"
    http_response = requests.get(bing_url, headers=headers)
    response_data = json.loads(http_response.content)
    if response_data["totalEstimatedMatches"] > 0:
        return response_data["value"][0]["contentUrl"]
    else:
        return None

def get_nutrient_information(ingredient_name):
    open_food_repo_url = "https://www.foodrepo.org/api/v3/products/_search"
    headers = {}
    headers["Authorization"] = 'Token token="<OPEN FOOD REPO TOKEN>"'

    request_body =  {
                        "_source": {
                            "includes": [
                                "nutrients"
                            ]
                        },
                        "size": 20,
                        "query": {
                            "query_string": {
                                "query" : ingredient_name + "~"
                            }
                        }
                    }
    
    http_response = requests.post(open_food_repo_url, headers = headers, data=json.dumps(request_body))
    response_data = json.loads(http_response.content)
    nutrient_information = ""
    
    if response_data["hits"]["total"] > 0:
        nutrients_dict = response_data["hits"]["hits"][0]["_source"]["nutrients"]
        if not nutrients_dict:
            return nutrient_information
        else:
            nutrient_information = nutrient_information + "Nutrient information for product: \n"
            if "carbohydrates" in nutrients_dict:
                nutrient_information = nutrient_information + f"carbohydrates: {nutrients_dict['carbohydrates']['per_hundred']} / 100{nutrients_dict['carbohydrates']['unit']} \n"
            if "salt" in nutrients_dict:
                nutrient_information = nutrient_information + f"salt: {nutrients_dict['salt']['per_hundred']} / 100{nutrients_dict['salt']['unit']} \n"
            if "sugars" in nutrients_dict:
                nutrient_information = nutrient_information + f"sugars: {nutrients_dict['sugars']['per_hundred']} / 100{nutrients_dict['sugars']['unit']} \n"
            if "protein" in nutrients_dict:
                nutrient_information = nutrient_information + f"protein: {nutrients_dict['protein']['per_hundred']} / 100{nutrients_dict['protein']['unit']} \n"
            if "fat" in nutrients_dict:
                nutrient_information = nutrient_information + f"fat: {nutrients_dict['fat']['per_hundred']} / 100{nutrients_dict['fat']['unit']} \n"
            if "saturated_fat" in nutrients_dict:
                nutrient_information = nutrient_information + f"saturated fat: {nutrients_dict['saturated_fat']['per_hundred']} / 100{nutrients_dict['saturated_fat']['unit']} \n"
            if "energy_kcal" in nutrients_dict:
                nutrient_information = nutrient_information + f"energy: {nutrients_dict['energy_kcal']['per_hundred']} / 100g"
    return nutrient_information


def clear_name(ingredient):
    if "," in ingredient:
        index = ingredient.index(",")
        ingredient = ingredient[0 : int(index)]
    
    if "or" in ingredient:
        index = ingredient.index("or")
        ingredient = ingredient[0 : int(index)]
    
    regex = re.compile(".*?\((.*?)\)")
    to_remove = re.findall(regex, ingredient)
    for word in to_remove:
        ingredient = ingredient.replace(word, "")
    
    regex = re.compile('[^a-zA-Z ]')
    ingredient = regex.sub("", ingredient)

    ingredient_words = ingredient.split()
    indexes = []
    for i in range(0, len(ingredient_words)):
        if len(ingredient_words[i]) < 3:
            indexes.append(i)
        
        if ingredient_words[i] in quantity_words:
            indexes.append(i)
    
    for i in indexes:
        ingredient_words[i] = ""

    ingredient = " ".join(ingredient_words)

    return ingredient.strip().lower()

