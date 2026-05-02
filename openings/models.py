from django.db import models


class OpeningBook(models.Model):
    eco = models.CharField(max_length=8, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    pgn = models.TextField()
    epd = models.CharField(max_length=100, unique=True, db_index=True)

    class Meta:
        db_table = "opening_book"
        ordering = ["eco", "name"]
        verbose_name = "Opening"
        verbose_name_plural = "Openings"

    def __str__(self):
        return f"{self.eco} — {self.name}"
