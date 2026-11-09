# Codigo 1

- La funcion c deberia renombrarse a algo que describa su utilidad
- Las variables no estan bien definidas y deberian tener nombres claros
- Las variables deberian tener nombres como promedio, suma.
- No se sabe de que es la lista.

## Reescrito
```python
def promedio(notas):
    suma = 0
    for nota in notas:
        suma = suma + nota
    promedio = suma / len(notas)
    return promedio
```

# Codigo 2

- Añadir constantes de nota minima de aprobado, nota maxima (7.0) 
    y ruta de archivo.
- Separar funcionalidades como guardar archivo, verificar nota,
    calcular promedio.

# Código 3

- La funcion proc tiene un nombre poco descriptivo, deberia ser calcular_cargos.
- Los nombres d, i, v, t, p, q, h y n no explican que hacen, como facturas, item, importe.
- Los valores c y s representan tipos de cobros y se deberian llamar como tal.
- La logica para aplicar el descuento del 10 % está duplicada en ambas ramas.
- Los valores 50000, 0.9 y 4.33 son números mágicos se tienen que nombrar en constantes.
- La función calcula resultados distintos según el tipo de elemento, pero concentra toda la logica en un solo lugar.
- La variable res podría tener un nombre como resultados.

